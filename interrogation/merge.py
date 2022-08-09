from __future__ import unicode_literals
from email import message
from inspect import trace
import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage, ButtonsTemplate, MessageTemplateAction
import configparser
import random
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import pandas as pd
import math

# 引用私密金鑰
cred = credentials.Certificate('serviceAccount.json')

# 初始化firebase，注意不能重複初始化
firebase_admin.initialize_app(cred)

# 初始化firestore
db = firestore.client()

# 
data = pd.read_csv('特徵矩陣.csv')
data = data.sample(frac=1, random_state=1).reset_index(drop=True) # 將資料順序打亂，以便後續進行cross validation
p0 = pd.read_csv('p0.csv', index_col="Disease")
p1 = pd.read_csv('p1.csv', index_col="Disease")

label = data['Disease']
Diseases = label.unique()
symptoms = data.drop(["Disease"], axis=1).columns

from flask_ngrok import run_with_ngrok
app = Flask(__name__)


#----- handle word (word segmentation、fuzzywuzzy、remove common symptom) ----------------------------------
import jieba
from ArticutAPI import Articut
def word_segmentation(input_message): # word segmentation and remove stopword
    seg_word = ""
    articut = Articut(username="", apikey="")
    result = articut.parse(input_message)
    contentWordLIST = articut.getContentWordLIST(result)
    
    print("----- word_segmentation -----")
    for sentence in contentWordLIST:
        for word in sentence:
            seg_word += word[-1]
            seg_word += " "
    print(seg_word)
    print("----- word_segmentation finish -----")
    
    feature = [i for i in fuzzywuzzy(seg_word)]
    transform_data = pd.DataFrame(data=None, columns=symptoms)
    transform_data.loc[len(transform_data)] = 0
    for i in range(len(feature)):
        if feature[i] == '':
            break
        transform_data.at[len(transform_data)-1, feature[i].replace(' ','')] = 1
    
    return transform_data

from fuzzywuzzy import fuzz
from fuzzywuzzy import process
def fuzzywuzzy(seg_word):
    f = open('userdict.txt',"r",encoding="utf-8")
    userdict = []
    for line in f:
        line = line.replace('\n', '')
        userdict.append(line)
    print(userdict)
    
    print("----- fuzzywuzzy -----")
    result = process.extract(seg_word, userdict)
    
    after_fuzz = []
    delete_symptom = []
    for i in range(len(result)):
        data, grade = result[i]
        if grade >= 90: # completely same
            after_fuzz.append(data)
        else:
            str_grade = str(grade)
            temp = data + ": " + str_grade
            delete_symptom.append(temp)
    
    print("score >= 90 (completely same):")
    for i in range(len(after_fuzz)):
        if (i + 1) != len(after_fuzz):
            print(after_fuzz[i], end = "，")
        else:
            print(after_fuzz[i])
    print(" ")

    print("score < 90 (sympyom: score):")
    for i in range(len(delete_symptom)):
        print(delete_symptom[i])

    print("----- fuzzywuzzy finish -----")
    
    return after_fuzz

import numpy as np 
def write_in_csv(after_fuzz):
    pass

#----- bayesian ------------------------------------------------------------------------------------------
def predict(mat):
    # 預測疾病並輸出機率矩陣
    Diseases = label.unique()
    symptoms = data.drop(["Disease"], axis=1).columns

    probArr = []
    for index, row in mat.iterrows():
        prob = {Disease: math.prod([p1.loc[Disease, sym] if row[sym] == 1 else p0.loc[Disease, sym] for sym in symptoms]) for Disease in Diseases}
        # 按比例縮放
        s = sum(prob.values())
        for key, value in prob.items():
            prob[key] = value / s
        probArr.append(prob)
        # predictArr.append(max(probArr, key=probArr.get))
    prob = probArr[0]
    prob = sorted(prob.items(), key=lambda x:  x[1], reverse=True)[:2]
    print(prob)
    return prob
#----- linebot ------------------------------------------------------------------------------------------
config = configparser.ConfigParser()
config.read('config.ini')
line_bot_api = LineBotApi(config.get('line-bot', 'channel_access_token'))
handler = WebhookHandler(config.get('line-bot', 'channel_secret'))

yourID = 'U2448be13ae578567931bd8c5e5fa51fa'

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    
    try:
        print(body, signature)
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
        
    return 'OK'

#----- handle message ----------------------------------------------------------------------------------
import re
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    input_message = event.message.text
    sym = word_segmentation(input_message)
    prob = predict(sym)
    reply_arr=[]
    for i in range(len(prob)):
        disease, rate = prob[i]
        rate = str(rate)
        if i == 0:
            reply_arr.append(TextSendMessage(text= "目前初步" + disease + " " + rate))
        else:
            reply_arr.append(TextSendMessage(text= "第" + str(i + 1) + "可能的" + disease + " " + rate))
    line_bot_api.reply_message(event.reply_token, reply_arr)
        
if __name__ == "__main__":
    run_with_ngrok(app) # 串連 ngrok 服務
    app.run()
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
import matplotlib.pyplot as plt
from sklearn.datasets import load_iris
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import cross_val_score, train_test_split
import pandas as pd
from sklearn import tree
import jieba
from ArticutAPI import Articut
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import numpy as np 
from glob import glob
import os



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

# from flask_ngrok import run_with_ngrok
app = Flask(__name__)


#----- handle word (word segmentation、fuzzywuzzy、remove common symptom) ----------------------------------

def word_segmentation(input_message,UserId): # word segmentation and remove stopword
    seg_word = []
    articut = Articut(username="", apikey="")
    result = articut.parse(input_message)
    contentWordLIST = articut.getContentWordLIST(result)
    
    print("----- word_segmentation -----")
    for sentence in contentWordLIST:
        for word in sentence:
            seg_word.append(word[-1])
    print(seg_word)
    # after_seg_word = replace_synonym(seg_word)
    after_seg_word = seg_word
    print(after_seg_word)
    temp = ""
    for i in range(len(after_seg_word)):
        temp += after_seg_word[i]
        temp += ' '
    seg_word=temp
    print(seg_word)
    print("----- word_segmentation finish -----")
    

    feature = [i for i in fuzzywuzzy(seg_word,UserId)]
    transform_data = pd.DataFrame(data=None, columns=symptoms)
    transform_data.loc[len(transform_data)] = 0
    for i in range(len(feature)):
        if feature[i] == '':
            break
        transform_data.at[len(transform_data)-1, feature[i].replace(' ','')] = 1
    return transform_data


def fuzzywuzzy(seg_word,UserId):
    f = open('userdict.txt',"r",encoding="utf-8")
    userdict = []
    for line in f:
        line = line.replace('\n', '')
        userdict.append(line)
    # print(userdict)
    
    print("----- fuzzywuzzy -----")
    result = process.extract(seg_word, userdict)
    
    after_fuzz = []
    delete_symptom = []
    for i in range(len(result)):
        data, grade = result[i]
        if grade >= 90: # completely same
            after_fuzz.append(data)
            # with open('afterfuzz.txt', 'a+') as f:
            #     f.write(data)
        else:
            str_grade = str(grade)
            temp = data + ": " + str_grade
            delete_symptom.append(temp)
    for i in range(len(after_fuzz)):
        with open(UserId+'afterfuzz.txt', 'a',encoding="utf_8") as f:
            f.write(after_fuzz[i])
            f.write("\n")
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




#----- replace_synonym ------------------------------------------------------------------------------------------
def replace_synonym(seg_word):
    file = open('同義詞.csv', 'r', encoding='utf-8-sig')
    words = [line.replace('\n', '').split(',') for line in file]

    for i in range(len(seg_word)):
        for word in words:
            if seg_word[i] in word:
                seg_word[i] = word[0]
    return seg_word

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
#----- decision tree ------------------------------------------------------------------------------------------
def decisiontree(UserId):
    disease = pd.read_csv('特徵矩陣1.csv')
    diseases = disease['Disease'].unique()
    print(diseases)
    # test = pd.read_csv('testing矩陣.csv')
    # tests = test['Disease'].unique()
    # print(tests)
    afpredict = []
    f = open(UserId+'disease.txt', 'r', encoding="utf_8")
    lines = f.readlines()
    for line in lines:
        line = line.replace("\n", "")
        afpredict.append(line)

    after_fuzz = []
    f = open(UserId+'afterfuzz.txt', 'r', encoding="utf_8")
    lines = f.readlines()
    for line in lines:
        line = line.replace("\n", "")
        after_fuzz.append(line)

    linebot_diseases = afpredict
    for ld in linebot_diseases:
        for d in diseases:
            if ld == d:
                new_diseases = disease[disease['Disease'] == d]
                new_diseases.to_csv(f'{UserId}_disease_csv_{d}.csv', index=False, encoding='utf_8_sig')  #索引值不匯出到CSV檔案中
                break



    # for ld in linebot_diseases:
    #     for t in tests:
    #         if ld == t:
    #             new_test = test[test['Disease'] == t]
    #             new_test.to_csv(f'test_csv_{t}.csv', index=False, encoding='utf_8_sig')  #索引值不匯出到CSV檔案中
    #             break
    disease_files = glob(UserId+'_disease_csv*.csv')
    print(disease_files)
    # test_files = glob('test_csv*.csv')
    # print(test_files)
    test = pd.read_csv('testing矩陣.csv')
    list_test = list(test)
    print(list_test)

    after_concat_disease = pd.concat((pd.read_csv(file, dtype={'Disease': str}) for file in disease_files), axis='rows')
    for ld in linebot_diseases:
        for d in diseases:
            if ld == d:
                file=UserId+'_disease_csv_'+d+'.csv'
                os.remove(file)
                break
    after_concat_disease.to_csv(f'after_concat_disease.csv', index=False, encoding='utf_8_sig')

    for a in after_fuzz:
        for t in list_test:
            if a == t:
                test[t] = 1
    test.to_csv(f'after_testing.csv', index=False, encoding='utf_8_sig')

    training = pd.read_csv('after_concat_disease.csv')
    testing = pd.read_csv('after_testing.csv')

    cols = training.columns
    cols = cols[:-1]
    x = training[cols]
    y = training['Disease']

    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.3, random_state=0)

    clf1 = DecisionTreeClassifier()
    clf = clf1.fit(x_train, y_train)
    scores = cross_val_score(clf, x_test, y_test, cv=2) # cv=5
    print(scores)
    print(f'Score: {scores.mean()}')

    with open(UserId+"_disease-tree.dot", 'w', encoding='utf-8') as f:
        f = tree.export_graphviz(clf, out_file=f, class_names=clf.classes_, feature_names=cols)

# ----- binary method -------------------------------------
def binary_method(UserId):
    f = open(UserId+'_disease-tree.dot','r')
    dict_node = {}
    dict_leave = {}
    dict_path = {}

    with open(UserId+'_disease-tree.dot', encoding="utf-8") as f:
        data = f.readlines()[2:-1]

    for i in range(len(data)):
    #     print(data[i])
        if data[i][2] == "[":
            judge = data[i].find("<")
            if judge != -1: # node
                temp_label = ''
                for j in range(10, (judge - 1)):
                    temp_label += data[i][j]

                temp_node = data[i][0]
                temp = {temp_node: temp_label}
                dict_node.update(temp)
            else: # leave
                judge2 = data[i].find("class")
                temp_label = ''
                for j in range((judge2 + 8), (len(data[i]) - 5)):
                    temp_label += data[i][j]
                temp_node = data[i][0]
                temp = {temp_node: temp_label}
                dict_leave.update(temp)
        elif data[i][2] == "-":
            if data[i][0] not in dict_path.keys():
                start = data[i][0]
            else:
                start = data[i][0] + "'"
            finish = data[i][5]
            temp = {start: finish}
            dict_path.update(temp)
    print(dict_node, dict_leave, dict_path)

    node_list = list(dict_node.values())
    leave_list = list(dict_leave.values())
    # print(node_list, leave_list)

    traversal(node_list, leave_list,UserId)
    
    # temp = ""
    # for i in range(len(temp_list)):
    #     temp += temp_list[i]
    #     if i != (len(temp_list) - 1):
    #         temp += '、'
    # print("需要分的疾病: " + temp)
    # print(list(dict_node.keys()))

# ----- traversal -------------------------------------
def traversal(node_list, leave_list,UserId):
    class node:
      def __init__(self, value):
        self.val = value
        self.left = None
        self.right = None
      def setLeft(self, left):
        self.left = left
      def setRight(self, right):
        self.right = right 

    p0 = node(node_list[0])
    root = p0
    p1 = node(node_list[1])
    p2 = node(leave_list[0])
    p3 = node(leave_list[1])
    p4 = node(leave_list[2])

    p0.setLeft(p1)
    p0.setRight(p4)
    p1.setLeft(p2)
    p1.setRight(p3)

    traversal = []
    traversal.append("0\n")
    def preorder(p):
      if p:
        traversal.append(p.val)
        traversal.append("\n")
        preorder(p.left);
        preorder(p.right);

    preorder(root)
#     print(traversal)
    
    f = open(UserId+'_traversal.txt', 'w')
    f.writelines(traversal)
    f.close()

def inquiry(ans,UserId):
    traversal = []
    f = open(UserId+'_traversal.txt', 'r')
    lines = f.readlines()
    for line in lines:
        line = line.replace("\n", "")
        traversal.append(line)
    print(traversal)
    
    inquiry_sym = "None"
    final_disease = "None"
    num = int(traversal[0])
    print(type(num))
    
    
    if ans == "start":
        inquiry_sym = traversal[1]

    if num == 0:
        if ans == True:
            final_disease = traversal[5]
            print(num)
            print(ans)
            print(final_disease)
            print(traversal[5])
        if ans == False:
            inquiry_sym = traversal[2]
            line_to_replace = 0
            with open(UserId+'_traversal.txt', 'r') as file:                     
                lines = file.readlines()
                if len(lines) > int(line_to_replace):
                    lines[line_to_replace] = '1\n'   #new为新参数，记得加换行符\n
            with open(UserId+'_traversal.txt', 'w') as file:
                file.writelines( lines )
    elif num == 1: # num == 1
        if ans == True:
            final_disease = traversal[4]
        if ans == False:
            final_disease = traversal[3]
    
    return [inquiry_sym, final_disease]

#----- linebot ------------------------------------------------------------------------------------------
config = configparser.ConfigParser()
config.read('config.ini')
line_bot_api = LineBotApi(config.get('line-bot', 'channel_access_token'))
handler = WebhookHandler(config.get('line-bot', 'channel_secret'))

# yourID = 'U2448be13ae578567931bd8c5e5fa51fa'

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
    
    if event.message.text == "是":
        UserId = event.source.user_id
        inquiry_arr = inquiry(True,UserId)
        print(inquiry_arr)
        traversal = []
        f = open(UserId+'_traversal.txt', 'r')
        lines = f.readlines()
        for line in lines:
            line = line.replace("\n", "")
            traversal.append(line)
        
        if inquiry_arr[0] != "None":
            line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(text= "請問是否有" + inquiry_arr[0] + "的症狀?", actions=[MessageTemplateAction(label= "是", text= "是"), MessageTemplateAction(label= "否", text= "否")])))
        if inquiry_arr[1] != "None":
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text = "診斷為" + inquiry_arr[1]))
    
    elif event.message.text == "否":
        UserId = event.source.user_id
        inquiry_arr = inquiry(False,UserId)
        
        traversal = []
        f = open(UserId+'_traversal.txt', 'r')
        lines = f.readlines()
        for line in lines:
            line = line.replace("\n", "")
            traversal.append(line)
        
        if inquiry_arr[0] != "None":
            line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(text= "請問是否有" + inquiry_arr[0] + "的症狀?", actions=[MessageTemplateAction(label= "是", text= "是"), MessageTemplateAction(label= "否", text= "否")])))
        if inquiry_arr[1] != "None":
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text = "診斷為" + inquiry_arr[1]))
    else:
        input_message = event.message.text
        UserId = event.source.user_id
        sym = word_segmentation(input_message,UserId)
        prob = predict(sym)

        reply_arr=[]
        dis_arr=[]
        for i in range(len(prob)):
            disease, rate = prob[i]
            rate = str(rate)
            if i == 0:
                reply_arr.append(TextSendMessage(text= "目前初步" + disease + " " + rate))
                dis_arr.append(disease)
            else:
                reply_arr.append(TextSendMessage(text= "第" + str(i + 1) + "可能的" + disease + " " + rate))
                dis_arr.append(disease)
        for i in range(len(dis_arr)):
            with open(UserId+'disease.txt', 'a',encoding="utf_8") as f:
                f.write(dis_arr[i])
                f.write("\n")
        decisiontree(UserId)
        # os.remove(r'afterfuzz.txt')
        # os.remove(r'disease.txt')
        line_bot_api.reply_message(event.reply_token, reply_arr)
        binary_method(UserId)
        binary_check = False
        disease, rate = prob[0]
        disease2, rate2 = prob[1]
        if abs(rate2 - rate) < 1: # 是否要做二分法的判斷條件
            binary_check = True

        if binary_check == True:
            binary_method(UserId)
            inquiry_arr = inquiry("start",UserId)
            line_bot_api.push_message(UserId, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(title= "發現有症狀機率相似，做二分法", text= "請問是否有" + inquiry_arr[0] + "的症狀?", actions=[MessageTemplateAction(label= "是", text= "是"), MessageTemplateAction(label= "否", text= "否")])))
        
if __name__ == "__main__":
#     run_with_ngrok(app) # 串連 ngrok 服務
    app.run()
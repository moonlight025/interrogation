from __future__ import unicode_literals
from email import message
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

# 引用私密金鑰
cred = credentials.Certificate('serviceAccount.json')

# 初始化firebase，注意不能重複初始化
firebase_admin.initialize_app(cred)

# 初始化firestore
db = firestore.client()

#----- write user's info in/out firebase ---------------------------------------------------------------
def write_in(input_message, reply_message):
    doc = {
        '使用者輸入': input_message,
        'linebot回覆': reply_message
    }
    
    # 語法
    # doc_ref = db.collection("集合名稱").document("文件id")
    doc_ref = db.collection("from_linebot").document("text")
    
    doc_ref.set(doc)
    
def write_out():
    path = "disease/cough"
    doc_ref = db.document(path)
    try:
        doc = doc_ref.get()
        # 透過 to_dict()將文件轉為dictionary
        print("文件內容為：{}".format(doc.to_dict()))
        doc = doc.to_dict()
        doc = doc['description']
    except:
        print("指定文件的路徑{}不存在，請檢查路徑是否正確".format(path))
        
    return doc

from flask_ngrok import run_with_ngrok
app = Flask(__name__)

#----- handle word (word segmentation、fuzzywuzzy、remove common symptom) ----------------------------------
import jieba
from ArticutAPI import Articut
def word_segmentation(input_message): # word segmentation and remove stopword
    seg_word = []
    articut = Articut(username="", apikey="")
    result = articut.parse(input_message)
    contentWordLIST = articut.getContentWordLIST(result)
    
    print("----- word_segmentation -----")
    for sentence in contentWordLIST:
        for word in sentence:
            seg_word.append(word[-1])
            print(seg_word[-1])
    print("----- word_segmentation finish -----")
    
    DB_template = fuzzywuzzy(seg_word)
    
    # print("------word_segmentation DB_template--------------")
    # for k in range(len(DB_template)):
    #     print(DB_template[k])
    return DB_template

from fuzzywuzzy import fuzz
# from fuzzywuzzy import process
def fuzzywuzzy(seg_word):
    # get symptom's names from firebase
    DB_symptom = []
    path = "symptom"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc = doc['name']
        DB_symptom.append(doc)
    
    # handle fuzzywuzzy
    after_fuzz = []
    print("----- fuzzywuzzy -----")
    for i in range(len(seg_word)):
        for j in range(len(DB_symptom)):
            score = fuzz.partial_ratio(seg_word[i], DB_symptom[j])
            print(seg_word[i], DB_symptom[j], score)
            if score >= 50:
                after_fuzz.append(DB_symptom[j])
                print("!!! 「 " + seg_word[i] + " 」 changes into 「 " + DB_symptom[j] + " 」, and adds in Array \" after_fuzz \".")
    print("----- fuzzywuzzy finish -----")
    
    if len(after_fuzz) != 0:
        DB_template = common_symptom(after_fuzz)
    else:
        DB_template = "您輸入的描述經判斷後無法辨認是何種症狀，請再輸入其他的症狀。"
        print("All of these neither in Database \" symptom \" nor bigger than 50.")
    
    # print("------fuzzywuzzy DB_template--------------")
    # for k in range(len(DB_template)):
    #     print(DB_template[k])
    return DB_template

def common_symptom(after_fuzz): # whether common symptom
    # get common symptom's names from firebase
    DB_common = []
    path = "common_symptom"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc = doc['name']
        DB_common.append(doc)
    
    # remove common symptom
    after_common = []
    common = False
    print("----- common symptom -----")
    for i in range(len(after_fuzz)):
        for j in range(len(DB_common)):
            if after_fuzz[i] == DB_common[j]:
                common = True
                print("XXX 「 " + after_fuzz[i] + " 」corresponds to Database \" common_symptom \" 's " + DB_common[j] + " , and be removed.")
                
        if common == False:
            after_common.append(after_fuzz[i])
            print("!!! 「 " + after_fuzz[i] + " 」 isn't  common symptom, so adds in Array \" after_common \".")
        
        common = False
    print("----- common symptom finish -----")
    
    # for k in range(len(after_common)):
    #     print(after_common[k])    
    
    if len(after_common) != 0:
        storage_after_common(after_common)
        after_order = order_by_frequency(after_common)
        DB_template = disease(after_order)
    else:
        DB_template = "您輸入的描述經判斷後皆為常見症狀，請再輸入其他的症狀。"
        print("All of these are common symptom.")

    # print("------common DB_template--------------")
    # for k in range(len(DB_template)):
    #     print(DB_template[k])
    return DB_template

def storage_after_common(after_common):
    # storage after_common in firebase, for "reply yes"
    doc = {
        'text': after_common
    }
    
    print("----- storage after_common -----")
    doc_ref = db.collection("after_common").document("DB_after_common")
    doc_ref.set(doc)
    print("----- storage after_common finish -----")

def read_after_common():
    # get after_common from firebase
    print("----- read after_common -----")
    path = "after_common"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc_text = doc['text']
    print("----- read after_common finish -----")

    return doc_text
    
def order_by_frequency(after_common):
    # get disease's names from firebase
    DB_name = []
    path = "disease"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for i in range(len(after_common)):
        for doc in docs:
            doc = doc.to_dict()
            doc_name = doc['name']
            doc_disease_name = doc['disease_name']
            if after_common[i] == doc_name:
                DB_name.append(doc_disease_name)
    
    # count  frequency
    frequency = []
    frequency.append(DB_name[0])  # frequency[even] = symptom
    frequency.append("1")  # frequency[odd] = frequency
    for i in range(1, len(DB_name)):
        flag = False
        for j in range(0, len(frequency), 2):
            if DB_name[i] == frequency[j]:
                flag = True
                temp = int(frequency[(j + 1)]) # type problem
                temp  += 1
                frequency[(j + 1)] = str(temp)
                break
        
        if flag == False:
            frequency.append(DB_name[i])
            frequency.append("1")
    
    # order by frequency descend
    if len(frequency) == 4:
        if frequency[1] > frequency[3]:
            frequency[0], frequency[2] = frequency[2], frequency[0]
            frequency[1], frequency[3] = frequency[3], frequency[1]
    else:
        for i in range(int((len(frequency) / 2) - 2)):
            for j in range(0, (len(frequency) - (i * 2) - 2), 2):
                if frequency[(j + 1)] > frequency[(j + 3)]:
                    frequency[j], frequency[(j + 2)] = frequency[(j + 2)], frequency[j]
                    frequency[(j + 1)], frequency[(j + 3)] = frequency[(j + 3)], frequency[(j + 1)]            
    # print("------frequency--------------")
    # for k in range(len(frequency)):
    #     print(frequency[k])
    
    after_order = []
    print("----- order by frequency -----")
    if len(frequency) == 2:
        print("「 " + frequency[i] + " 」: " + frequency[(i + 1)] + " 次")
        after_order.append(frequency[i])
    else:
        for i in range((len(frequency) - 2), -1, -2):
            print("「 " + frequency[i] + " 」: " + frequency[(i + 1)] + " 次")
            after_order.append(frequency[i])
    print("----- order by frequency finish -----")
    
    return after_order
    
def disease(after_order):
    # get disease's description from firebase
    DB_template = ["1"] # "1" is count_index, for "reply one outcome at one time"
    path = "disease"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for i in range(len(after_order)):
        for doc in docs:
            doc = doc.to_dict()
            doc_disease_name = doc['disease_name']
            doc_description = doc['description']
            if after_order[i] == doc_disease_name:
                DB_template.append(doc_description)

    print("----- disease -----")
    for k in range(len(DB_template)):
        print(DB_template[k])
    print("----- disease finish -----")
    
    storage_template(DB_template)
    return DB_template

def storage_template(DB_template):
    # storage template in firebase, for "reply one outcome at one time"
    doc = {
        'text': DB_template
    }
    
    print("----- storage template -----")
    doc_ref = db.collection("storage_template").document("DB_template")
    doc_ref.set(doc)
    print("----- storage template finish -----")
    
def read_template():
    # get DB_template from firebase
    print("----- read template -----")
    path = "storage_template"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc_text = doc['text']
    print("----- read template finish -----")

    return doc_text

def remove_negation(negation):
    # clear Database "user_negation"'s DB_negation
    if negation == "end":
        doc = {
            'text': []
        }
        
        print("----- clear DB_negation -----")
        doc_ref = db.collection("user_negation").document("DB_negation")
        doc_ref.set(doc)
        print("----- clear DB_negation finish -----")
        
        return
    
    # get disease's names from firebase
    path = "disease"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc_description = doc['description']
        doc_disease_name = doc['disease_name']
        if negation == doc_description:
            new_negation = doc_disease_name
            
    # get user's negation from firebase
    path = "user_negation"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc_text = doc['text']
        doc_text.append(new_negation)
    
    # storage new_negation in firebase, for binary method
    doc = {
        'text': doc_text
    }
    
    print("----- storage new negation -----")
    doc_ref = db.collection("user_negation").document("DB_negation")
    doc_ref.set(doc)
    print("----- storage new negation finish -----")

def inquire_word(DB_template):
    # according to after_common, select disease's symptom from firebase
    count_index = DB_template[0]
    count_index = int(count_index)
    template_description = DB_template[count_index]
    
    print("----- inquire_word(select) -----")
    global new_affirmation  # !!!!!! global new_affirmation之後要刪掉 為了二分法寫的
    affirmation = []
    disease_name = ""
    path = "disease"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc_description = doc['description']
        doc_name = doc['name']
        doc_disease_name = doc['disease_name']
        if template_description == doc_description:
            affirmation.append(doc_name)
            disease_name = doc_disease_name
    
    after_common = read_after_common()
    new_affirmation = []
    for i in range(len(after_common)):
        for j in range(len(affirmation)):
            if after_common[i] == affirmation[j]:
                new_affirmation.append(after_common[i])
            
    print("user affirmative disease: " + disease_name)
    print("after selecting's symptom : ", end = "")
    for i in range(len(new_affirmation)):
        print(new_affirmation[i], end = " ")
    print("\n----- inquire_word(select) finish -----")
    
    print("----- inquire_word(inquire word) -----")
    inquire_word = ["1"]
    flag = False
    path = "binary_method"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc_disease_name = doc['disease_name']
                
        if disease_name == doc_disease_name:
            doc_text = doc['text']
            for i in range(len(doc_text)):
                for j in range(len(new_affirmation)):
                    if doc_text[i] == new_affirmation[j]:
                        flag = True
                    
                if flag == False:
                    inquire_word.append(doc_text[i])
                
                flag = False
        
    print("inquire word: ", end = "")
    for i in range(len(inquire_word)):
        print(inquire_word[i], end = " ")
    print("\n----- inquire_word(inquire word) finish -----")
    
    storage_inquire_word(inquire_word)
    return inquire_word

def storage_inquire_word(inquire_word):
    # storage inquire word in firebase, for "binary_method()"
    doc = {
        'text': inquire_word
    }
    
    print("----- storage inquire word -----")
    doc_ref = db.collection("inquire_word").document("inquire")
    doc_ref.set(doc)
    print("----- storage inquire word finish -----")
    
def read_inquire_word():
    # get inquire_word from firebase
    print("----- read inquire word -----")
    path = "inquire_word"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc_text = doc['text']
    print("----- read inquire word finish -----")

    return doc_text

def storage_count_yes_no(count_yes, count_no):
    # storage count_yes and count_no in firebase, for "binary_method()"
    doc = {
        'affirmation': count_yes,
        'negation': count_no
    }
    
    print("----- storage count_yes and count_no -----")
    doc_ref = db.collection("count_times").document("count")
    doc_ref.set(doc)
    print("----- storage count_yes and count_no finish -----")

def read_count_yes_no():
    # get count_yes and count_no from firebase
    print("----- read count_yes and count_no -----")
    path = "count_times"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    doc_text = []
    for doc in docs:
        doc = doc.to_dict()
        doc_affirmation = doc['affirmation']
        doc_text.append(doc_affirmation)
        doc_negation = doc['negation']
        doc_text.append(doc_negation)
    print("----- read count_yes and count_no finish -----")

    return doc_text

def binary_method(judgment):
    # get "inquire_word" and "count" from Database inquire_word and Database count_times
    doc_inquire_word = []
    path = "inquire_word"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        doc_inquire_word = doc['text']
    
    count_yes = 0
    count_no = 0
    path = "count_times"
    collection_ref = db.collection(path)
    docs = collection_ref.get()
    for doc in docs:
        doc = doc.to_dict()
        count_yes = doc['affirmation']
        count_no = doc['negation']
    
    # judgment
    if judgment == True:
        count_yes += 1
    else:
        count_no += 1
    
    print("----- binary method -----")
    after_common = read_after_common()
    if len(after_common) != 0: # select affirmation
        if doc_inquire_word[0] == "1": # first time binary method
            count_yes += len(new_affirmation)          # !!!!!! global new_affirmation之後要刪掉 為了二分法寫的
        
        str_inquire_word = doc_inquire_word[0]
        int_inquire_word = int(str_inquire_word)
        int_inquire_word += 1
        str_inquire_word = str(int_inquire_word)
        doc_inquire_word[0] = str_inquire_word
        storage_inquire_word(doc_inquire_word)
        storage_count_yes_no(count_yes, count_no)
        
    else: # in the beginning or all negation
        pass
    
    print("count_index :" + doc_inquire_word[0])
    str_count_yes = str(count_yes)
    print("affirmation: " + str_count_yes)
    str_count_no = str(count_no)
    print("negation: " + str_count_no)
    print("----- binary method finish -----")

#----- linebot ------------------------------------------------------------------------------------------
config = configparser.ConfigParser()
config.read('config.ini')
line_bot_api = LineBotApi(config.get('line-bot', 'channel_access_token'))
handler = WebhookHandler(config.get('line-bot', 'channel_secret'))

yourID = 'U2a2b8c039d29e10d49f5298b3ee7f502'
line_bot_api.push_message(yourID, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(title= "您好，我是clinic-smart，負責初步診斷您的病情。", text= "請選擇「手動輸入」或「由我提問」。", actions=[MessageTemplateAction(label= "手動輸入", text= "手動輸入"), MessageTemplateAction(label= "由我提問", text= "由我提問")])))

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
    # if event.message.text == "貧血":
    #     line_bot_api.reply_message(event.reply_token,TextSendMessage(text="地中海貧血"))
    #     input_message = event.message.text
    #     reply_message = "地中海貧血"
    #     write_in(input_message, reply_message)
    # elif event.message.text == "咳嗽":
    #     from_firebase = write_out()
    #     line_bot_api.reply_message(event.reply_token,TextSendMessage(text= from_firebase))

    #----- reply one outcome at one time -----------------------------------------------------------
    yourID = 'U2a2b8c039d29e10d49f5298b3ee7f502'

    if event.message.text == "是":
        DB_template = read_template()
        
        if len(DB_template) != 1:
            after_common = read_after_common()
            if len(after_common) <= 3:
                global inquire_word # solved UnboundLocalError
                inquire = inquire_word(DB_template)
                str_index = inquire[0]
                int_index = int(str_index)
                line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(title= "那請問您有" + inquire[int_index] + "的症狀嗎?", text= "請選擇「有」或「無」。", actions=[MessageTemplateAction(label= "有", text= "有"), MessageTemplateAction(label= "無", text= "無")])))
                
            else:
                line_bot_api.push_message(yourID, TextSendMessage(text="謝謝，很高興能幫助您。"))
                temp_DB_template = ["1"]
                DB_template = temp_DB_template
                storage_template(DB_template)
                
                DB_negation = "end"
                remove_negation(DB_negation)
                
                after_common = []
                storage_after_common(after_common)
                
                temp_inquire_word = ["1"]
                inquire_word = temp_inquire_word
                storage_inquire_word(inquire_word)
                
                count_yes = 0
                count_no = 0
                storage_count_yes_no(count_yes, count_no)
            
    elif event.message.text == "否":
        DB_template = read_template()
        str_count_index = DB_template[0]
        int_count_index = int(str_count_index)
        if len(DB_template) != 1: # avoid user enter "否" in the beginning
            remove_negation(DB_template[(int_count_index)])
            int_count_index += 1
            str_count_index = str(int_count_index)
            DB_template[0] = str_count_index
            
            if  (int_count_index) <= (len(DB_template) - 1):
                # line_bot_api.push_message(yourID, TextSendMessage(text="不好意思，那第" + str_count_index + "可能的" + DB_template[int_count_index]))
                # line_bot_api.push_message(yourID, TextSendMessage(text="請問這個診斷您是是否滿意?"))
                # line_bot_api.push_message(yourID, TextSendMessage(text="請輸入「是」或「否」。"))
                line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(title= "不好意思，那第" + str_count_index + "可能的" + DB_template[int_count_index], text= "請問這個診斷您是是否滿意? 請選擇「是」或「否」。", actions=[MessageTemplateAction(label= "是", text= "是"), MessageTemplateAction(label= "否", text= "否")])))
                
                storage_template(DB_template)
                
            else:
                line_bot_api.push_message(yourID, TextSendMessage(text="不好意思，請再輸入其他的症狀加以判斷。"))
                temp_DB_template = ["1"]
                DB_template = temp_DB_template
                storage_template(DB_template)
                
                after_common = []
                storage_after_common(after_common)
    
    #----- for binary method -----------------------------------------------------------
    elif event.message.text == "有":
        DB_template = read_template()
        if len(DB_template) != 1:
            judgment = True
            binary_method(judgment)
            
            count_yes_no = read_count_yes_no()
            count_yes = count_yes_no[0]
            count_no = count_yes_no[1]
            
            if count_yes >= 3:
                line_bot_api.push_message(yourID, TextSendMessage(text="謝謝，很高興能幫助您。"))
                temp_DB_template = ["1"]
                DB_template = temp_DB_template
                storage_template(DB_template)
                
                DB_negation = "end"
                remove_negation(DB_negation)
                
                after_common = []
                storage_after_common(after_common)
                
                temp_inquire_word = ["1"]
                inquire_word = temp_inquire_word
                storage_inquire_word(inquire_word)
                
                count_yes = 0
                count_no = 0
                storage_count_yes_no(count_yes, count_no)
            
            elif count_no >= 3:
                pass
            
            else:
                inquire = read_inquire_word()
                str_index = inquire[0]
                int_index = int(str_index)
                line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(title= "那請問您有" + inquire[int_index] + "的症狀嗎?", text= "請選擇「有」或「無」。", actions=[MessageTemplateAction(label= "有", text= "有"), MessageTemplateAction(label= "無", text= "無")])))
            
    elif event.message.text == "無":
        DB_template = read_template()
        if len(DB_template) != 1:
            judgment = False
            binary_method(judgment)
            
            count_yes_no = read_count_yes_no()
            count_yes = count_yes_no[0]
            count_no = count_yes_no[1]
            
            if count_yes >= 3:
                line_bot_api.push_message(yourID, TextSendMessage(text="謝謝，很高興能幫助您。"))
                temp_DB_template = ["1"]
                DB_template = temp_DB_template
                storage_template(DB_template)
                
                DB_negation = "end"
                remove_negation(DB_negation)
                
                after_common = []
                storage_after_common(after_common)
                
                temp_inquire_word = ["1"]
                inquire_word = temp_inquire_word
                storage_inquire_word(inquire_word)
                
                count_yes = 0
                count_no = 0
                storage_count_yes_no(count_yes, count_no)
            
            elif count_no >= 3:
                pass
            
            else:
                inquire = read_inquire_word()
                str_index = inquire[0]
                int_index = int(str_index)
                line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(title= "那請問您有" + inquire[int_index] + "的症狀嗎?", text= "請選擇「有」或「無」。", actions=[MessageTemplateAction(label= "有", text= "有"), MessageTemplateAction(label= "無", text= "無")])))
                
    elif event.message.text == "手動輸入":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請將您目前有的症狀全部輸入成一句話，謝謝。"))
    
    elif event.message.text == "由我提問":
        pass
    
    else:
        input_message = event.message.text
        DB_template = word_segmentation(input_message)
        print("----- DB_template -----")
        print(DB_template)
        print("----- DB_template finish -----")
        
        # #----- reply all outcomes in once (!!! max == 5) ----------------------------------------------
        # reply_arr=[]
        # for i in range(len(DB_template)):
        #     if i == 0:
        #         reply_arr.append(TextSendMessage(text= "目前初步" + DB_template[0]))
        #     else:
        #         reply_arr.append(TextSendMessage(text= "第" + str(i + 1) + "可能的" + DB_template[i]))
        # line_bot_api.reply_message(event.reply_token, reply_arr)
        
        #----- reply one outcome at one time -----------------------------------------------------------
        # line_bot_api.reply_message(event.reply_token,TextSendMessage(text= "目前初步" + DB_template[1]))
        # line_bot_api.push_message(yourID, TextSendMessage(text="請問這個診斷您是是否滿意?"))
        # line_bot_api.push_message(yourID, TextSendMessage(text="(請輸入「是」或「否」。"))
        line_bot_api.reply_message(event.reply_token, TemplateSendMessage(alt_text='Buttons template', template=ButtonsTemplate(title= "目前初步" + DB_template[1], text= "請問這個診斷您是是否滿意? 請選擇「是」或「否」。", actions=[MessageTemplateAction(label= "是", text= "是"), MessageTemplateAction(label= "否", text= "否")])))
        
if __name__ == "__main__":
    run_with_ngrok(app) # 串連 ngrok 服務
    app.run()
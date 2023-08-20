import functions_framework
import datetime
import os
import json
import secrets

from flask import abort

from linebot import (
  LineBotApi, WebhookHandler
)
from linebot.exceptions import (
  InvalidSignatureError
)
from linebot.models import (
  MessageEvent, TextMessage, TextSendMessage
)

from google.cloud import logging
from google.cloud import firestore

import langchain
langchain.debug = True

from langchain.agents import (
  AgentType, load_tools, initialize_agent
)
from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage
from langchain.prompts import MessagesPlaceholder
from langchain.memory.buffer_window import ConversationBufferWindowMemory
from langchain.memory.chat_message_histories import FirestoreChatMessageHistory
from langchain.agents import AgentExecutor

logging_client = logging.Client()
logger_name = "gpt_line_bot"
logger = logging_client.logger(logger_name)

db = firestore.Client()

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])
model_name = os.environ.get('CHAT_MODEL_NAME', default="gpt-3.5-turbo-0613")

llm = ChatOpenAI(model_name=model_name, temperature=0, request_timeout=120)

# set search tool name. "google-serper", "google-search", etc.
search_tool = 'google-serper'
tools = load_tools([search_tool, 'pubmed', 'arxiv', 'llm-math'], llm=llm)

def get_sess_id(event:MessageEvent) -> str:
  sess_id = "sess" + secrets.token_hex(16)
  if event.source.type == "user":
    sess_id = event.source.type + event.source.user_id
  elif event.source.type == "group":
    sess_id = event.source.type + event.source.group_id
  elif event.source.type == "room":
    sess_id = event.source.type + event.source.room_id
  return sess_id

system_message = """あなたは優秀なAIアシスタントです。回答の手順は以下のとおりです。

1. 回答に必要な情報を得るために、適切な関数を実行して、必要な情報を得ます。
2. 1.で得られた情報をもとに、依頼や質問に対する回答を作成します。
3. 回答に必要な情報が得られない場合や、有害な回答となる場合は、回答できない理由を述べて謝罪します。
"""

def get_agent_executor(event: MessageEvent) -> AgentExecutor:
  sess_id = get_sess_id(event)
  message_history = FirestoreChatMessageHistory(collection_name="gpt_line_bot",
                                                session_id=datetime.date.today().strftime("%Y-%m-%d"),
                                                user_id=sess_id,
                                                firestore_client=db)
  memory = ConversationBufferWindowMemory(memory_key="memory",
                                          k=5,
                                          return_messages=True,
                                          chat_memory=message_history)

  agent_kwargs = {
    "system_message": SystemMessage(content=system_message),
    "extra_prompt_messages": [MessagesPlaceholder(variable_name="memory")]
  }

  agent_executor = initialize_agent(tools=tools,
                                    llm=llm,
                                    agent=AgentType.OPENAI_MULTI_FUNCTIONS,
                                    agent_kwargs=agent_kwargs,
                                    memory=memory,
                                    verbose=True)
  
  return agent_executor


def send_log(user_id:str, message:str, response:str) -> None:
  data = {
    "user_id": user_id,
    "message": message,
    "response": response,
  }
  json_data = json.dumps(data)
  logger.log_struct(json.loads(json_data))

@functions_framework.http
def main(request):
  """HTTP Cloud Function.
  Args:
    request (flask.Request): The request object.
    <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
  Returns:
    The response text, or any set of values that can be turned into a
    Response object using `make_response`
    <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
  """
  signature = request.headers['X-Line-Signature']

  body = request.get_data(as_text=True)

  try:
    handler.handle(body, signature)
  except InvalidSignatureError:
    print("Invalid signature. Please check your channel access token/channel secret.")
    abort(400)
 
  return 'OK'
  
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
  try:
    agent_executor = get_agent_executor(event)
    response = agent_executor.run(input=event.message.text)
  except Exception as e:
    response = str(e)
    print(response)
    if not response.startswith("Could not parse LLM output: "):
      response = '大変申し訳ありません。エラーが発生したため、回答できません。: ' + response
    else:
      # 回答が得られているが、Parse Errorになる場合のアドホックな対応
      response = response[len("Could not parse LLM output: "):]
    
  line_bot_api.reply_message(
    event.reply_token,
    TextSendMessage(text=response))
  
  send_log(event.source.user_id, event.message.text, response)

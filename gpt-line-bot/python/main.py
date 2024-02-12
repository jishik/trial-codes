import functions_framework
import datetime
import os
import json
import secrets
import traceback

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

from langchain import hub
from langchain.agents import (
  AgentExecutor,
  create_openai_tools_agent,
  load_tools
)
from langchain_openai import ChatOpenAI
from langchain.memory.buffer_window import ConversationBufferWindowMemory
from langchain_community.chat_message_histories import FirestoreChatMessageHistory
from langchain.agents import AgentExecutor

logging_client = logging.Client()
logger_name = "gpt_line_bot"
logger = logging_client.logger(logger_name)

db = firestore.Client()

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])
model_name = os.environ.get('CHAT_MODEL_NAME', default="gpt-3.5-turbo")

def get_sess_id(event:MessageEvent) -> str:
  sess_id = "sess" + secrets.token_hex(16)
  if event.source.type == "user":
    sess_id = event.source.type + event.source.user_id
  elif event.source.type == "group":
    sess_id = event.source.type + event.source.group_id
  elif event.source.type == "room":
    sess_id = event.source.type + event.source.room_id
  return sess_id

def get_agent_executor(memory=None) -> AgentExecutor:
  llm = ChatOpenAI(model_name=model_name, temperature=0, request_timeout=120)

  # set search tool name. "google-serper", "google-search", etc.
  search_tool = 'google-serper'
  tools = load_tools([search_tool, 'pubmed', 'arxiv', 'llm-math'], llm=llm)
  
  prompt = hub.pull("hwchase17/openai-tools-agent")

  agent = create_openai_tools_agent(llm, tools, prompt)
  
  agent_executor = AgentExecutor(agent=agent, tools=tools, memory=memory, verbose=True)
  
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
    sess_id = get_sess_id(event)
    message_history = FirestoreChatMessageHistory(collection_name="gpt_line_bot",
                                                session_id=datetime.date.today().strftime("%Y-%m-%d"),
                                                user_id=sess_id,
                                                firestore_client=db)
    memory = ConversationBufferWindowMemory(k=10,
                                            chat_memory=message_history,
                                            input_key="input")
    
    agent_executor = get_agent_executor(memory)
    response = agent_executor.invoke({
                                      "input": event.message.text,
                                      "chat_history": memory.buffer_as_messages
                                      })
    response = response["output"]
  except Exception as e:
    traceback.print_exc()
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

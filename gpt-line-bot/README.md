# gpt-line-bot

ChatGPTを利用して回答を行うLINE Botのwebhookのサンプルコードです。
GCPのCloud Functionでwebhookの関数を実行します。

[LangChain](https://github.com/hwchase17/langchain)を使って実装
しており、質問に対して、Google検索を実行した結果を使って、回答を返します。

以下のAPIやサービスを利用するため、アカウント登録や設定が必要です。過去の
登録状況・利用状況等により、クレジットカードの登録が必要な場合や無料枠の
範囲を超える場合がありますので、各サイトをご確認の上、ご自身の責任で登録・
利用するようにしてください。

* [OpenAI API](https://openai.com/blog/openai-api)
* [Line Messaging API](https://developers.line.biz/ja/services/messaging-api/)
* [Serper](https://serper.dev/) (LangChainのtoolsで”google-serper”を指定する場合)
* [Google Custom Search API](https://programmablesearchengine.google.com/) (LangChainのtoolsで"google-search"を指定する場合)
* [Google Cloud Platform](https://cloud.google.com/)

上記の各APIのkey等について、以下の環境変数をCloud Functionの変数として
設定する必要があります。keyの入手方法やCloud Functionの環境変数の設定に
ついては、各サイトの説明を参照してください。

* OPEN_API_KEY
* LINE_CHANNEL_ACCESS_TOKEN
* LINE_CHANNEL_SECRET
* SERPER_API_KEY
* GOOGLE_CSE_ID
* GOOGLE_API_KEY

会話ログの履歴をGCPのFirestoreに保存しています。GCP ProjectのFirestore
を有効にする必要があります。

gcloudコマンドで、Cloud Functionをデプロイするには、以下のコマンドを
実行します。
```
gcloud functions deploy gpt-line-bot \
--gen2 \
--runtime=python311 \
--source=./python \
--entry-point=main \
--trigger-http \
--region=<region> \
--allow-unauthenticated
```

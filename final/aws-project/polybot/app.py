import flask
from flask import request
import os
from bot import ObjectDetectionBot, Bot
import boto3
from botocore.exceptions import ClientError
import json

app = flask.Flask(__name__)


def get_secret():
    secret_name = "hamad-telegram-token"
    region_name = "eu-north-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        logging.info(f"client error has occurred : {e} ")
        raise e
    except Exception as e:
        raise e
    secret = get_secret_value_response['SecretString']
    secret_data = json.loads(secret)
    
    # Access the value associated with the 'TOKEN' key
    telebot_value = secret_data['telegram-token']
    
    return telebot_value

TELEGRAM_TOKEN = get_secret()
# TODO : Change TELEGRAM_APP_URL to the route 53 domain name and make the ingress 
TELEGRAM_APP_URL = os.environ["LOAD_BALANCER"]
  
@app.route('/', methods=['GET'])
def index():
    return 'Ok'


@app.route(f'/{TELEGRAM_TOKEN}/', methods=['POST'])
def webhook():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'

@app.route(f'/results/', methods=['GET'])
def results():
    prediction_id = request.args.get('predictionId')

    # Use the prediction_id to retrieve results from DynamoDB
    # Assuming you have a function to retrieve data from DynamoDB
    results, chat_id, desc = retrieve_results_from_dynamodb(prediction_id)
       
    # Send the results to the end-user via the Telegram bot
    bot.send_text_result(chat_id, desc)
    
    return 'Ok'


def retrieve_results_from_dynamodb(prediction_id):
    # Create a DynamoDB client
    dynamodb = boto3.client('dynamodb', region_name='eu-north-1')

    # Specify the name of the DynamoDB table
    table_name = 'hamad-telegram-bot'#TODO change table name 

    try:
        # Get item from DynamoDB table using prediction_id as the key
        response = dynamodb.get_item(
            TableName=table_name,
            Key={'prediction_id': {'S': prediction_id}}
        )
        
        # Extract the item from the response
        item = response.get('Item')
        
        if item:
            # Extract the chat ID and description from the item
            chat_id = item.get('chat_id', {}).get('S')
            description = json.loads(item.get('description', {}).get('S', '{}'))
            return item, chat_id, description
        else:
            return None, None, None
            
    except dynamodb.exceptions.ResourceNotFoundException:
        return None, None, None



def format_results(results_description):

    return results_description



@app.route(f'/loadTest/', methods=['POST'])
def load_test():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'
    
if __name__ == "__main__":
    bot = ObjectDetectionBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL)

    app.run(host='0.0.0.0', port=8443)
    print("app running")
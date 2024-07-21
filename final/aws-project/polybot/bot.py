import json

import requests
import telebot
from botocore.exceptions import ClientError
from loguru import logger
import os
import time
from telebot.types import InputFile
import boto3


def get_secret():
    secret_name = "hamad-pixabay-token"
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
        raise e

    secret = get_secret_value_response['SecretString']
    

    secret_data = json.loads(secret)
    
    # Access the value associated with the 'pixabay_token' key
    telebot_value = secret_data['pixabay_token']
    
    return telebot_value



class Bot:

    def __init__(self, token, telegram_chat_url):
        # create a new instance of the TeleBot class.
        # all communication with Telegram servers are done using self.telegram_bot_client
        self.telegram_bot_client = telebot.TeleBot(token)

        # remove any existing webhooks configured in Telegram servers
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)

        # todo set the webhook URL change path in ec2 docker container
        self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/',
                                             certificate=open('YOURPUBLIC.pem', 'r'),
                                             timeout=60)

        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')
    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        """
        Downloads the photos that sent to the Bot to `photos` directory (should be existed)
        :return:
        """
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')

        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]

        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        with open(file_info.file_path, 'wb') as photo:
            photo.write(data)

        return file_info.file_path

    def send_photo(self, chat_id, img_path):
        if not os.path.exists(img_path):
            raise RuntimeError("Image path doesn't exist")

        self.telegram_bot_client.send_photo(
            chat_id,
            InputFile(img_path)
        )

    def handle_message(self, msg):
        """Bot Main message handler"""
        logger.info(f'Incoming message: {msg}')
        self.send_text(msg['chat']['id'], f'Your original message: {msg["text"]}')


# pixabay_token = os.environ['PIXABAY_TOKEN']
def get_photo(param: str):
    param.replace(" ", "")
    pixabay_token = get_secret()
    url = f"https://pixabay.com/api/?key={pixabay_token}&q={param[8:].lower()}&image_type=photo"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            first_large_image_url = ""
            for hit in data["hits"]:
                if "largeImageURL" in hit:
                    logger.info(f"check {hit['largeImageURL']}")
                    first_large_image_url = hit["largeImageURL"]
                    break
            if first_large_image_url:
                return first_large_image_url
            else:
                logger.info("No images found.")
                return "No images found."
        else:
            logger.error(f"Failed to fetch data: HTTP Status Code {response.status_code}")
            return f"Error: Unable to access Pixabay API, received status code {response.status_code}"
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return "Error: An issue occurred while attempting to fetch the photo."


def get_info_of_currency(currency: str):
    currency.replace(" ", "")
    try:
        url = f"https://api.coincap.io/v2/assets/{currency}"
        data = requests.get(url)
        return data.json()
    except Exception as e:
        print(f"could not get the url check if you typed the right currency {e}")
        logger.info(f"error {e}")


def get_activity():
    try:
        url = "https://www.boredapi.com/api/activity?type=recreational"
        res = requests.get(url)
        return res.json()
    except Exception as e:
        logger.info(f"error has occurred {e}")


class ObjectDetectionBot(Bot):
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')

        if self.is_current_msg_photo(msg):
            photo_path = self.download_user_photo(msg)
            photo_key = os.path.basename(photo_path)
            self.download_user_photo(msg)
            # TODO upload the photo to S3
            s3 = boto3.client('s3')
            try:
                s3.upload_file(photo_path, "hamad-bucket-docker-project", photo_key)

                print(
                    f"Photo uploaded successfully to S3 bucket: {'hamad-bucket-docker-project'} with key: {photo_key}")
            except Exception as e:
                print(f"could not upload error : {e}")
                logger.info(f"uploading to s3 has failed error : {e}")
            # TODO send a job to the SQS queue

            sqs = boto3.client("sqs")
            queue_url = "https://sqs.eu-north-1.amazonaws.com/933060838752/hamad-aws-project-sqs"
            try:
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=photo_key + "," + msg['chat']['id']
                )
            except Exception as e:
                print(f"could not send message to sqs queue error : {e}")
                logger.info(f"sending message to sqs queue has failed error : {e}")

            # TODO send message to the Telegram end-user (e.g. Your image is being processed. Please wait...)
            self.send_text(msg["chat"]["id"], "Your image is being processed. Please wait...")
        elif msg["text"].lower().startswith("pixabay:"):
            try:
                image_url = get_photo(msg['text'])
                if image_url.startswith("http"):  # Simple check to ensure it's a URL
                    logger.info(f" ###############{msg}")
                    self.send_text(msg['chat']['id'], f"Image URL: {image_url}")
                else:
                    self.send_text(msg['chat']['id'], "Failed to fetch image from Pixabay.")
            except Exception as e:
                logger.error(f"Cannot get photo: {e}")
                self.send_text(msg['chat']['id'], "An error occurred while fetching the photo.")
        elif msg['text'].lower().startswith("crypto:"):
            try:
                data = get_info_of_currency(msg['text'].lower()[7:])
                self.send_text(msg['chat']['id'],
                               f"data for {msg['text'][7:]} is :\n {json.dumps(data['data'], indent=4)}")
            except Exception as e:
                logger.info(f"error has occurred : {e}")
        elif "bored" in msg['text'].lower():
            try:
                activity = get_activity()
                self.send_text(msg['chat']['id'], activity['activity'])
            except Exception as e:
                logger.info(f"error fetching data {e}")
        else:
            logger.info("helllloooooooo")
            super().handle_message(msg)
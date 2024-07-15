import base64
import io
import json
import requests
import telebot
from loguru import logger
import os
import time
import boto3
from telebot.types import InputFile
from botocore.exceptions import ClientError

# def get_k8s_secret1(namespace, secret_name):
#         # Load kubeconfig from default location or specified path
#         config.load_kube_config()  # Use config.load_incluster_config() if running inside a pod

#         # Create an instance of the CoreV1Api
#         v1 = client.CoreV1Api()

#         try:
#             # Retrieve the secret
#             secret = v1.read_namespaced_secret(secret_name, namespace)
#             return secret.data
#         except client.exceptions.ApiException as e:
#             print(f"Exception when calling CoreV1Api->read_namespaced_secret: {e}")
#             return None
        
class Bot:
    
    
    

    def __init__(self, token, telegram_chat_url):
        print(telegram_chat_url)
        print(token)

        # create a new instance of the TeleBot class.
        # all communication with Telegram servers are done using self.telegram_bot_client
        self.telegram_bot_client = telebot.TeleBot(token)
        #TODO put the certificate in the k8s secret and pull from there and change the code here
        # remove any existing webhooks configured in Telegram servers
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)
        # namespace = "hamad"  # Replace with your namespace
        # secret_name = "tls-secret-hamad"  # Replace with your secret name
        # secret = get_k8s_secret1(namespace, secret_name)
        # Create a file-like object from the PEM string
        # print("##################################1####################################")
        # print(secret)
        # print("################################2######################################")
        # pem_file = io.StringIO(secret)
        # print("###############################3#######################################")
        # print(type(pem_file))
        # print("###############################4#######################################")
        # print(pem_file)
        # print("###############################5#######################################")

        # #self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', timeout=60)
        # response = self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', certificate=open(pem_file,'r'))#TODO check if it works it may not 

        # print(response)
        # logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')
        # with open('', 'r') as file: # TODO pull the certificate from the k8s secret
        #   pem_contents = file.read()
        #   print(pem_contents)
        # set the webhook URL
        # session = boto3.session.Session()
        # client = session.client(
        #     service_name='secretsmanager',
        #     region_name="eu-north-1"
        # )
        # secret_response  = client.get_secret_value(
        #     SecretId="hamad-telegram-cert"
        # )

        # pem_contents = secret_response['SecretString']
        # print(pem_contents)
        # # set the webhook URL
        # # Create a file-like object from the PEM string
        # pem_file = io.StringIO(pem_contents)
        # #self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', timeout=60)
        # response = self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', certificate=pem_file)
        # print(response)
        # logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')
        client = boto3.session.Session().client(
            service_name='secretsmanager',
            region_name="eu-north-1"
        )
        secret_response = client.get_secret_value(
            SecretId="hamad-telegram-cert"
        )
        pem_contents = secret_response['SecretString']
        json_contents = json.loads(pem_contents)
        # print(json_contents["hamad-cert"])
        secret = io.StringIO(json_contents["hamad-cert"].replace(" ", "\n").replace("-----BEGIN\nCERTIFICATE-----", "-----BEGIN CERTIFICATE-----").replace("-----END\nCERTIFICATE-----", "-----END CERTIFICATE-----"))
        # set the webhook URL
        # Create a file-like object from the PEM string
        #self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', timeout=60)
        print("##################################1####################################")
        print(secret.read())
        print("################################2######################################")
        response = self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', certificate=secret.read())
        print(response)
        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')
    

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)
    
    def send_text_result(self, chat_id, desc_json):
        class_counts = {}
        for item in desc_json:
            class_name = item.get("class")
            if class_name:
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
    
        message = ""
        for class_name, count in class_counts.items():
            message += f"{class_name}: {count}\n"
        
        self.telegram_bot_client.send_message(chat_id, message)
      
        
    
    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)
        

    @staticmethod
    def is_current_msg_photo(msg):
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

        self.telegram_bot_client.send_photo(chat_id,InputFile(img_path))

    def handle_message(self, msg):
        """Bot Main message handler"""
        logger.info(f'Incoming message: {msg}')
        if 'text' in msg:
            self.send_text(msg['chat']['id'], f'3 :Your original message: {msg["text"]}')
        else:
            self.send_text(msg['chat']['id'], "Sorry, I couldn't process your message.")


class QuoteBot(Bot):
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')

        if msg["text"] != 'Please don\'t quote me':
            self.send_text_with_quote(msg['chat']['id'], msg["text"], quoted_msg_id=msg["message_id"])


class ObjectDetectionBot(Bot):
    def handle_message(self, msg):
        if self.is_current_msg_photo(msg):
            # Download the user photo
            photo_path = self.download_user_photo(msg)
            photo_key = os.path.basename(photo_path)

            # Upload the photo to S3
            s3 = boto3.client('s3')
            s3.upload_file(photo_path, "hamad-aws-project", photo_key)
            logger.info(f"Photo uploaded successfully to S3 bucket: 'hamad-aws-project' with key: {photo_key}")

            # Send a message to SQS for processing
            message = {
                'image': photo_key,
                'chat_id': msg['chat']['id']
            }
            self.send_message_to_sqs(json.dumps(message))
        elif self.custom_startswith(msg["text"], "pixabay:"):
            # Handle Pixabay API request
            obj = msg["text"][len("pixabay:"):]
            url2 = f"http://pixabay:8082/getImage?imgName={obj}"
            data2 = requests.get(url2).content
            self.send_text(msg['chat']['id'], f'Your Photo from Pixabay API: {data2} \n')
        else:
            # Handle other messages
            super().handle_message(msg)

    def custom_startswith(self, s, prefix):
        return s.startswith(prefix)

    def send_message_to_sqs(self, message_json):
        try:
            # Deserialize the JSON string to a dictionary
            message = json.loads(message_json)

            # Create an SQS client
            sqs = boto3.client('sqs', region_name="eu-north-1")
            # SQS queue URL TODO change the sqs url my sqs url or use rabbitmq or kafka 
            queue_url = 'https://sqs.eu-north-1.amazonaws.com/933060838752/hamad-aws-project-sqs'

            # Add MessageGroupId parameter
            response = sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=message_json,  # Send the original JSON string as message body                  
            )

            logger.info("Message successfully sent to SQS: %s", response['MessageId'])
            # Send a success message back to the user
            #self.send_text(message['chat_id'], 'Message successfully sent to SQS \n')
        except (ClientError, json.JSONDecodeError) as e:
            logger.error("Error sending message to SQS: %s", e)
            # Send an error message back to the user
            #self.send_text(message['chat_id'], f'Error sending message to SQS: {str(e)} \n')






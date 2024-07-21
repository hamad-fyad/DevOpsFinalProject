import time
from pathlib import Path
import boto3
from flask import Flask, request, jsonify
from detect import run
import yaml
from loguru import logger
import os
import json
import requests

# Initialize AWS resources and clients
images_bucket = os.environ['BUCKET_NAME']
queue_name = os.environ['SQS_QUEUE_NAME']
sqs_client = boto3.client('sqs', region_name='eu-north-1')

# Load YOLO class names from YAML file
with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']

# Define the insertData function to store data in DynamoDB
def insertData(prediction_id, filename, data, chat_id):
    dynamodb = boto3.client('dynamodb', region_name='eu-north-1')
    table_name = 'hamad-aws-project-db'#TODO change table name 
    item = {
        'prediction_id': {'S': prediction_id},
        'chat_id': {'S': str(chat_id)},
        'description': {'S': json.dumps(data)}
    }
    response = dynamodb.put_item(TableName=table_name, Item=item)
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        logger.info("Item stored successfully")
    else:
        logger.error("Failed to store item:", response['ResponseMetadata']['HTTPStatusCode'])

# Define the retrieve_results_from_dynamodb function
def retrieve_results_from_dynamodb(prediction_id):
    dynamodb = boto3.client('dynamodb', region_name='eu-north-1')
    table_name = 'hamad-aws-project-db' #TODO change table name
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={'prediction_id': {'S': prediction_id}}
        )
        item = response.get('Item')
        if item:
            chat_id = item.get('chat_id', {}).get('S')
            return item, chat_id
        else:
            return None, None
    except dynamodb.exceptions.ResourceNotFoundException:
        return None, None

# Define the consume function to process messages from SQS
def consume():
    while True:
        response = sqs_client.receive_message(QueueUrl=queue_name, MaxNumberOfMessages=1, WaitTimeSeconds=5)
        if 'Messages' in response:
            message = response['Messages'][0]['Body']
            receipt_handle = response['Messages'][0]['ReceiptHandle']
            prediction_id = response['Messages'][0]['MessageId']
            existing_result, _ = retrieve_results_from_dynamodb(prediction_id)
            if existing_result:
                logger.info(f'Prediction {prediction_id} already exists in the database. Skipping processing.')
                sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)
                continue
            logger.info(f'prediction: {prediction_id}. start processing')
            message_body = message
            params = json.loads(message_body)
            img_name = params['image']
            chat_id = params['chat_id']
            bucket_name = os.getenv('BUCKET_NAME')
            original_img_path = str(img_name)
            s3 = boto3.client('s3')
            s3.download_file(bucket_name, img_name, original_img_path)
            logger.info(f'prediction: {prediction_id}/{original_img_path}. Download img completed')
            run(weights='yolov5s.pt', data='data/coco128.yaml', source=original_img_path,
                project='static/data', name=prediction_id, save_txt=True)
            logger.info(f'prediction: {prediction_id}/{original_img_path}. done')
            predicted_img_path = Path(f'static/data/{prediction_id}/{original_img_path}')
            the_image = "predicted_" + original_img_path
            s3.upload_file(str(predicted_img_path), bucket_name, the_image)
            pred_summary_path = Path(f'static/data/{prediction_id}/labels/{original_img_path.split(".")[0]}.txt')
            if pred_summary_path.exists():
                with open(pred_summary_path) as f:
                    labels = f.read().splitlines()
                    labels = [line.split(' ') for line in labels]
                    labels = [{'class': names[int(l[0])], 'cx': float(l[1]), 'cy': float(l[2]),
                               'width': float(l[3]), 'height': float(l[4]), } for l in labels]
                logger.info(f'prediction: {prediction_id}/{original_img_path}. prediction summary:\n\n{labels}')
                prediction_summary = {
                    'prediction_id': prediction_id,
                    'original_img_path': original_img_path,
                    'predicted_img_path': predicted_img_path,
                    'labels': labels,
                    'time': time.time()
                }
                insertData(prediction_id, img_name, labels, chat_id)
                #TODO change url of the loadbalancer to my loadbalancer url
                url = f"https://hamad.atech-bot.click/results/?predictionId={prediction_id}"
                response = requests.get(url, verify=False)
            sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)

# Start consuming messages from SQS
if __name__ == "__main__":
    consume()

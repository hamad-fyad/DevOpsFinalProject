import time
from pathlib import Path
import boto3
from flask import Flask, request, jsonify
from detect import run
import uuid
import yaml
from loguru import logger
import os
import pymongo
import json
import requests

images_bucket = os.environ['BUCKET_NAME']
queue_name = os.environ['SQS_QUEUE_NAME']
alb = os.environ['LOAD_BALANCER']
table_name = os.environ['DYNAMO_TABLE']



sqs_client = boto3.client('sqs', region_name='eu-north-1')

with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']

# app = Flask(__name__)
# @app.route('/', methods=['GET'])
# def index():
#     return "Hello from yolo5"

def consume():
    while True:
        response = sqs_client.receive_message(QueueUrl=queue_name, MaxNumberOfMessages=1, WaitTimeSeconds=5)

        if 'Messages' in response:
            message = response['Messages'][0]['Body']
            receipt_handle = response['Messages'][0]['ReceiptHandle']

            # Use the ReceiptHandle as a prediction UUID
            prediction_id = response['Messages'][0]['MessageId']

            logger.info(f'prediction: {prediction_id}. start processing')

            # Assuming message_body contains the JSON string received from SQS
            message_body = message
            # Deserialize the JSON string into a Python dictionary
            params = json.loads(message_body)

            # Receives a URL parameter representing the image to download from S3
            img_name = params['image']
            chat_id = params['chat_id']
            message_id=params['message_id']
            #TODO download img_name from S3, store the local image path in original_img_path
            bucket_name = os.getenv('BUCKET_NAME')

            original_img_path = str(img_name)

            s3 = boto3.client('s3',region_name='eu-north-1')
            s3.download_file(bucket_name, img_name, original_img_path)


            logger.info(f'prediction: {prediction_id}/{original_img_path}. Download img completed')

            # Predicts the objects in the image
            run(
                weights='yolov5s.pt',
                data='data/coco128.yaml',
                source=original_img_path,
                project='static/data',
                name=prediction_id,
                save_txt=True
            )

            logger.info(f'prediction: {prediction_id}/{original_img_path}. done')

            # This is the path for the predicted image with labels
            # The predicted image typically includes bounding boxes drawn around the detected objects, along with class labels and possibly confidence scores.
            predicted_img_path = Path(f'static/data/{prediction_id}/{original_img_path}')

            # TODO Uploads the predicted image (predicted_img_path) to S3 (be careful not to override the original image).
            the_image = "predicted_" + original_img_path
            s3.upload_file(str(predicted_img_path), bucket_name, the_image)


            # Parse prediction labels and create a summary
            pred_summary_path = Path(f'static/data/{prediction_id}/labels/{original_img_path.split(".")[0]}.txt')
            if pred_summary_path.exists():
                with open(pred_summary_path) as f:
                    labels = f.read().splitlines()
                    labels = [line.split(' ') for line in labels]
                    labels = [{
                        'class': names[int(l[0])],
                        'cx': float(l[1]),
                        'cy': float(l[2]),
                        'width': float(l[3]),
                        'height': float(l[4]),
                    } for l in labels]

                logger.info(f'prediction: {prediction_id}/{original_img_path}. prediction summary:\n\n{labels}')

                prediction_summary = {
                    'prediction_id': prediction_id,
                    'original_img_path': original_img_path,
                    'predicted_img_path': predicted_img_path,
                    'labels': labels,
                    'time': time.time()
                }

                # TODO store the prediction_summary in a DynamoDB table
                insertData(prediction_id,img_name,labels,chat_id,message_id,table_name)

                # TODO perform a GET request to Polybot to `/results` endpoint
                url = f"{alb}/results/?predictionId={prediction_id}"
                # Send a GET request to the URL
                response = requests.get(url, verify=False)  # Set verify=False to ignore SSL certificate validation

            # Delete the message from the queue as the job is considered as DONE
            sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)

def insertData(prediction_id,filename,data,chat_id,message_id,table_name):

    # Create a DynamoDB client
    dynamodb = boto3.client('dynamodb',region_name='eu-north-1')

    # Create an item to store in the table
    item = {
        'prediction_id': {'S': prediction_id},
        'chat_id': {'S': str(chat_id)},
        'message_id': {'S': str(message_id)},
        'description': {'S': json.dumps(data)}
    }

    # Store the item in the DynamoDB table
    response = dynamodb.put_item(
        TableName=table_name,
        Item=item
    )

    # Check if the item was stored successfully
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        print("Item stored successfully")
    else:
        print("Failed to store item:", response['ResponseMetadata']['HTTPStatusCode'])


if __name__ == "__main__":
    # app.run(host='0.0.0.0', port=8081)
    consume()
from flask import Flask, request, jsonify, render_template, Response
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import queue
import threading
import time
import json
import requests
import math
import sys
app = Flask(__name__, template_folder='templates')
request_queue = queue.Queue()
processing = False
processing_thread = None
start_time = None
end_time = None


engine = create_engine("sqlite:///logs.db", echo=False)


Base = declarative_base()
# sys.set_int_max_str_digits(999999)
class ProcessedRequest(Base):
    __tablename__ = 'processed_requests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    input = Column(String)
    result = Column(String)
    timestamp = Column(DateTime)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


@app.route('/log')
def log():
    session = Session()
    requests = session.query(ProcessedRequest).all()
    print("Number of records:", len(requests))
    log_entries = [{"id": req.id, "input": req.input, "result": req.result,
                    "timestamp": req.timestamp.strftime('%Y-%m-%d %H:%M:%S')} for req in requests]
    print("Log entries:", log_entries)
    session.close()
    return jsonify(log_entries), 200

def process_requests():
    global processing
    while True:
        if not request_queue.empty():
            data = request_queue.get()
            input_value = data['number']
            result = str(calculate_factorial(input_value))
            print(f"Processing request: input={input_value}, result={result}")

            # Create a Python datetime object for the timestamp
            timestamp = datetime.now()

            session = Session()
            try:
                processed_request = ProcessedRequest(input=input_value, result=result, timestamp=timestamp)
                session.add(processed_request)
                session.commit()
                print("Request logged successfully")
            except Exception as e:
                session.rollback()
                print(f"Failed to log request: {str(e)}")
            finally:
                session.close()

            request_queue.task_done()
        else:
            time.sleep(1)

def calculate_factorial(n):
    if n == 0:
        return 1
    else:
        return str(math.factorial(n))


processing_thread = threading.Thread(target=process_requests)
processing_thread.start()

@app.route('/webhook', methods=['POST'])
def make_request():
    data = request.get_json()
    print("Received JSON data:", data)

    if data:
        for key, value in data.items():
            if isinstance(value, int):
                print(f"Received key: {key}, value: {value}")
                request_data = {'number': value}
                request_queue.put(request_data)

        return jsonify({"message": "Webhook received and enqueued for processing"}), 200
    else:
        print("Invalid webhook data:", data)
        return jsonify({"error": "Invalid webhook data"}), 400

@app.route('/')
def show_form():
    return render_template('form.html')
@app.route('/queue-status')
def queue_status():
    queue_size = request_queue.qsize()

    return jsonify({'size': queue_size}), 200
@app.route('/clear-log', methods=['POST'])
def clear_log():
    try:
        session = Session()
        session.query(ProcessedRequest).delete()
        session.commit()
        session.close()
        return jsonify({"message": "Log cleared successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to clear log: {str(e)}"}), 500

@app.route('/log-sse', methods=['GET'])
def log_sse():
    def event_stream():
        session = Session()
        last_processed_id = 0
        while True:
            requests = session.query(ProcessedRequest).filter(ProcessedRequest.id > last_processed_id).all()
            for req in requests:
                yield f"data: {json.dumps({'id': req.id, 'input': req.input, 'result': req.result, 'timestamp': req.timestamp.isoformat()})}\n\n"
                last_processed_id = req.id
            time.sleep(1)
            session.close()

    return Response(event_stream(), content_type='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)

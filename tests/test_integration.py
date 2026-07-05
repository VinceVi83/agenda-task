import pytest
import os
import time
import uuid
from datetime import datetime, timedelta
from conftest import make_api_request, wait_for_file, API_BASE_URL

import logging
logger = logging.getLogger(__name__)

def create_task(task_id, trigger_type, **kwargs):
    task = {'id': task_id, 'function': 'mcp_server.write_file_task', 
            'args': [f'/tmp/test_{task_id}.txt', f'Content for {task_id}'], 
            'trigger_type': trigger_type, 'status': 'active', 'skip_next': []}
    task.update(kwargs)
    return task

def test_1_one_shot_date_task():
    unique_id = str(uuid.uuid4())[:8]
    task_id = f'test_one_shot_api_{unique_id}'
    filepath = f'/tmp/test_{task_id}.txt'
    run_date = (datetime.now() + timedelta(seconds=20)).replace(microsecond=0).isoformat()
    task = create_task(task_id, 'date')
    task['run_date'] = run_date

    resp = make_api_request('POST', '/tasks', data=task)
    if not resp or resp.status_code != 200:
        error_msg = f"Task creation failed: {resp.status_code if resp else 'No response'}"
        if resp and hasattr(resp, 'text'):
            error_msg += f" - {resp.text}"
        assert False, error_msg
    tasks_resp = make_api_request('GET', '/tasks')
    if tasks_resp and tasks_resp.status_code == 200:
        tasks = tasks_resp.json().get('tasks', [])
        task_ids = [t['id'] for t in tasks]
        assert task_id in task_ids, f"Task {task_id} not found in scheduler tasks: {task_ids}"
    else:
        logger.info("WARNING: Could not get tasks list from scheduler")
    tasks = make_api_request('GET', '/tasks').json().get('tasks', [])
    assert any(t['id'] == task_id for t in tasks), "Task not found"
    assert wait_for_file(filepath, timeout=30), "Execution failed"
    make_api_request('DELETE', f'/tasks/{task_id}')

def test_2_cron_task_with_skip():
    unique_id = str(uuid.uuid4())[:8]
    task_id = f'test_cron_skip_api_{unique_id}'
    filepath = f'/tmp/test_{task_id}.txt'
    task = create_task(task_id, 'cron', cron={'second': '*/20', 'minute': '*', 'hour': '*', 'day': '*', 'month': '*', 'day_of_week': '*'})
    make_api_request('POST', '/tasks', data=task)
    resp = make_api_request('POST', f'/tasks/{task_id}/skip/0')
    assert resp and resp.status_code == 200, "Skip failed"
    if os.path.exists(filepath): os.remove(filepath)
    time.sleep(30)
    assert not os.path.exists(filepath), "The skip failed: the file exists"
    make_api_request('POST', f'/tasks/{task_id}/skip/0')
    assert resp and resp.status_code == 200, "Skip failed"
    assert wait_for_file(filepath, timeout=120), "Execution after skip failed"
    make_api_request('DELETE', f'/tasks/{task_id}')

def test_3_reschedule_with_expiry():
    unique_id = str(uuid.uuid4())[:8]
    task_id = f'test_reschedule_expiry_api_{unique_id}'
    filepath = f'/tmp/test_{task_id}.txt'
    task = create_task(task_id, 'cron', cron={'minute': '*', 'hour': '*', 'day': '*', 'month': '*', 'day_of_week': '*'})
    make_api_request('POST', '/tasks', data=task)

    res_data = {'new_cron_params': {'minute': '*/2', 'hour': '*'}, 'end_date': '2030-01-01T00:00:00'}
    resp = make_api_request('POST', f'/tasks/{task_id}/reschedule', data=res_data)
    assert resp and resp.status_code == 200, "Reschedule failed"
    assert wait_for_file(filepath, timeout=180), "Execution after reschedule failed"
    resp = make_api_request('GET', f'/tasks/{task_id}/next-execution')
    assert resp and resp.status_code == 200 and resp.json().get('success'), "The task was not reset correctly"
    make_api_request('DELETE', f'/tasks/{task_id}')


def test_4_reschedule_with_skip():
    unique_id = str(uuid.uuid4())[:8]
    task_id = f'test_reschedule_skip_api_{unique_id}'
    filepath = f'/tmp/test_{task_id}.txt'
    task = create_task(task_id, 'cron', cron={'minute': '*', 'hour': '*', 'day': '*', 'month': '*', 'day_of_week': '*'})
    make_api_request('POST', '/tasks', data=task)

    reschedule_data = {
        'new_cron_params': {
            'second': '*/20',
            'minute': '*',
            'hour': '*',
            'day': '*', 
            'month': '*',
            'day_of_week': '*'
        },
        'end_date': (datetime.now() + timedelta(minutes=10)).isoformat()
    }
    resp = make_api_request('POST', f'/tasks/{task_id}/reschedule', data=reschedule_data)
    assert resp and resp.status_code == 200, f"Reschedule failed: {resp.status_code if resp else 'No response'}"
    make_api_request('POST', f'/tasks/{task_id}/skip/0')
    if os.path.exists(filepath): os.remove(filepath)
    time.sleep(30)
    assert not os.path.exists(filepath), "The skip failed"
    make_api_request('POST', f'/tasks/{task_id}/skip/0')
    assert wait_for_file(filepath, timeout=40), "Execution occurred after skip"
    make_api_request('DELETE', f'/tasks/{task_id}')


def test_5_reschedule_and_reset():
    unique_id = str(uuid.uuid4())[:8]
    task_id = f'test_reschedule_reset_api_{unique_id}'
    filepath = f'/tmp/test_{task_id}.txt'
    task = create_task(task_id, 'cron', cron={'minute': '*', 'hour': '*', 'day': '*', 'month': '*', 'day_of_week': '*'})
    make_api_request('POST', '/tasks', data=task)
    reschedule_data = {
        'new_cron_params': {
            'second': '*/30',
            'minute': '*',
            'hour': '*',
            'day': '*', 
            'month': '*',
            'day_of_week': '*'
        },
        'end_date': (datetime.now() + timedelta(minutes=10)).isoformat()
    }
    resp = make_api_request('POST', f'/tasks/{task_id}/reschedule', data=reschedule_data)
    assert wait_for_file(filepath, timeout=40), "Reschedule execution failed"
    
    resp = make_api_request('POST', f'/tasks/{task_id}/reset-reschedule')
    assert resp and resp.status_code == 200, "Reset failed"
    if os.path.exists(filepath): os.remove(filepath)
    assert wait_for_file(filepath, timeout=120), "Execution after reset failed"
    make_api_request('DELETE', f'/tasks/{task_id}')

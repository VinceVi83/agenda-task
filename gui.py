import streamlit as st
import json
import os
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="Orchestrateur", layout="wide")

API_URL = "http://localhost:8888"
FUNCTIONS_FILE = "function_docs.json"

if "show_modal" not in st.session_state:
    st.session_state.show_modal = False

if "days_to_show" not in st.session_state:
    try:
        res = requests.get(f"{API_URL}/config")
        if res.status_code == 200:
            st.session_state.days_to_show = res.json().get("days_to_show", 7)
        else:
            st.session_state.days_to_show = 7
    except:
        st.session_state.days_to_show = 7


st.markdown("""
<style>
    [data-testid="stHeader"], [data-testid="stFooter"], #MainMenu {
        display: none !important;
        visibility: hidden !important;
    }
    .block-container {
        padding-top: 1.0rem !important;
        padding-bottom: 0rem !important;
    }
    hr {
        margin-top: 0.2rem !important;
        margin-bottom: 0.5rem !important;
    }
    .stTabs {
        margin-top: -1.0rem !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        height: calc(100vh - 200px) !important;
    }
    .header-container {
        display: flex;
        align-items: flex-end;
        gap: 20px;
        margin-bottom: 20px;
    }
    .title-part { font-size: 2.5rem; font-weight: bold; }
    .input-part { display: flex; align-items: center; gap: 10px; }
    .task-card-wrapper {
        padding: 10px;
        border-radius: 8px;
        border: 1px solid #30363d;
        margin-bottom: 10px;
        height: 140px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 2px;
        overflow: hidden;
        flex-shrink: 0;
    }
    .card-status { font-size: 0.75rem; font-weight: bold; margin: 0 0 2px 0; padding: 0; line-height: 1.1; }
    .card-id { 
        font-size: 1.1rem; 
        font-weight: bold; 
        margin: 0 0 4px 0; 
        padding: 0; 
        line-height: 1.2; 
        white-space: nowrap; 
        overflow: hidden; 
        text-overflow: ellipsis; 
    }
    .card-meta { font-size: 0.85rem; color: #8b949e; display: flex; align-items: center; gap: 5px; margin-bottom: 3px; }
    .card-tags { display: flex; gap: 5px; margin-top: auto; padding-top: 5px; }
    .card-line { font-size: 0.85rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; }
    .card-desc { 
        font-size: 0.8rem; 
        color: #8b949e; 
        line-height: 1.2; 
        display: -webkit-box; 
        -webkit-line-clamp: 2; 
        -webkit-box-orient: vertical; 
        overflow: hidden; 
        height: 2.4em;         
        margin-top: auto;      
    }
    .task-card-wrapper{ background-color: #1a2620; border-left: 5px solid #56d364; border-left: 5px solid #56d364;}
    .task-card-wrapper[data-state="paused"] { background-color: #26211a; border-left: 5px solid #ffa23e; }
    .task-card-wrapper[data-state="err"] { background-color: #261a1a; border-left: 5px solid #ff5a5a; }
    .task-card-wrapper[data-state="rescheduled"] {
        background-image: repeating-linear-gradient(
            45deg,
            transparent,
            transparent 10px,
            rgba(0, 191, 255, 0.15) 10px,
            rgba(0, 191, 255, 0.15) 20px
        );
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    .header-row {
        display: flex;
        align-items: center; 
        justify-content: flex-start;
        gap: 20px;
        margin-bottom: 20px;
        width: 100%;
    }
    .title-text { font-size: 2.5rem; font-weight: bold; white-space: nowrap; }
    .controls-row { display: flex; align-items: center; gap: 15px; }
</style>
""", unsafe_allow_html=True)


def load_tasks():
    try:
        response = requests.get(f"{API_URL}/tasks")
        if response.status_code == 200:
            tasks_dict = response.json().get("tasks", {})
            if isinstance(tasks_dict, list):
                return tasks_dict
            tasks_list = []
            for t_id, t_data in tasks_dict.items():
                if isinstance(t_data, dict):
                    t_data["id"] = t_id  
                    tasks_list.append(t_data)
            return tasks_list
    except Exception as e:
        st.error(f"API Error fetching tasks: {e}")
    return []


def load_functions():
    if not os.path.exists(FUNCTIONS_FILE):
        return {}
    try:
        with open(FUNCTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("functions", {})
    except:
        return {}


def get_cron_description(cron_dict):
    if not cron_dict:
        return "N/A"
    parts = []
    for k in ["minute", "hour", "day", "month", "day_of_week"]:
        v = cron_dict.get(k, "*")
        parts.append(v if v else "*")
    return " ".join(parts)


def get_next_executions(task, count=5):
    trigger_type = task.get("trigger_type", "cron")
    executions = []
    
    if trigger_type == "date":
        dt_str = task.get("run_date")
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str)
                if dt > datetime.now():
                    executions.append(dt)
            except:
                pass
        return executions

    cron = task.get("cron") or {}
    minute = cron.get("minute", "0")
    hour = cron.get("hour", "0")
    day = cron.get("day", "*")
    month = cron.get("month", "*")
    day_of_week = cron.get("day_of_week", "*")
    
    def parse_field(val, min_val, max_val):
        if val == "*":
            return list(range(min_val, max_val + 1))
        if "," in val:
            res = []
            for part in val.split(","):
                res.extend(parse_field(part, min_val, max_val))
            return sorted(list(set(res)))
        if "/" in val:
            base, step = val.split("/")
            step = int(step)
            start = min_val if base == "*" else int(base)
            return list(range(start, max_val + 1, step))
        if "-" in val:
            start, end = val.split("-")
            return list(range(int(start), int(end) + 1))
        return [int(val)]

    try:
        minutes = parse_field(minute, 0, 59)
        hours = parse_field(hour, 0, 23)
    except:
        minutes = [0]
        hours = [12]
        
    now = datetime.now()
    current = now.replace(second=0, microsecond=0)
    
    attempts = 0
    while len(executions) < count and attempts < 10000:
        current += timedelta(minutes=1)
        attempts += 1
        
        if current.minute not in minutes:
            continue
        if current.hour not in hours:
            continue
            
        if day != "*":
            try:
                days = parse_field(day, 1, 31)
                if current.day not in days:
                    continue
            except:
                pass
        if month != "*":
            try:
                months = parse_field(month, 1, 12)
                if current.month not in months:
                    continue
            except:
                pass
        if day_of_week != "*":
            try:
                dows = parse_field(day_of_week, 0, 6)
                dow_map = {0:6, 1:0, 2:1, 3:2, 4:3, 5:4, 6:5}
                current_dow = dow_map[current.weekday()]
                if current_dow not in dows:
                    continue
            except:
                pass
                
        executions.append(current)
        
    return executions


def is_task_on_day(task, target_date):
    if task.get("trigger_type") == "date":
        run_date_str = task.get("run_date") or task.get("date")
        if run_date_str:
            try:
                task_date = datetime.fromisoformat(str(run_date_str)).date()
                return task_date == target_date
            except:
                return False
                
    elif task.get("trigger_type") == "cron":
        cron = task.get("cron", {})
        dow_str = str(cron.get("day_of_week", "*"))
        
        if dow_str == "*":
            return True
            
        try:
            valid_days = []
            for part in dow_str.split(','):
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    valid_days.extend(range(start, end + 1))
                else:
                    valid_days.append(int(part))
            
            return target_date.weekday() in valid_days
        except:
            return False
            
    return False


def get_task_sort_key(t):
    if t.get("trigger_type") == "cron" and isinstance(t.get("cron"), dict):
        h = str(t["cron"].get("hour", "00")).zfill(2)
        m = str(t["cron"].get("minute", "00")).zfill(2)
        if "*" in h: h = "00"
        if "*" in m: m = "00"
        return f"{h}:{m}"
    else:
        d_str = t.get("date") or t.get("run_date")
        if d_str:
            try:
                return datetime.fromisoformat(str(d_str)).strftime("%H:%M")
            except:
                pass
    return "23:59"


def get_global_skip_index(target_task_id, target_date, all_tasks):
    chronology = []
    for i in range(7):
        day_date = datetime.now().date() + timedelta(days=i)
        tasks_on_day = sorted([t for t in all_tasks if is_task_on_day(t, day_date)], key=get_task_sort_key)
        for t in tasks_on_day:
            chronology.append({"date": day_date, "id": t['id']})

    target_occurrences = [item for item in chronology if item['id'] == target_task_id]
    
    for idx, occ in enumerate(target_occurrences):
        if occ['date'] == target_date:
            return idx + 1
            
    return 1


functions_data = load_functions()

if "data" not in st.session_state:
    st.session_state.data = load_tasks()
if "modal_mode" not in st.session_state:
    st.session_state.modal_mode = None
if "selected_task_id" not in st.session_state:
    st.session_state.selected_task_id = None

st.session_state.data = load_tasks()
tasks_data = st.session_state.data


@st.dialog("Task Configuration", width="large")
def render_task_modal():
    mode = st.session_state.modal_mode
    task_id = st.session_state.selected_task_id
    
    task = None
    if mode == "edit" and task_id:
        for t in st.session_state.data:
            if t["id"] == task_id:
                task = t
                break
                
    if mode == "edit" and not task:
        st.error("Task not found.")
        return

    if task is None:
        task = {}

    title_text = "Edit Task" if mode == 'edit' else "Add New Task"
    is_cron_task = task.get("trigger_type") == "cron"
    show_temp_checkbox = (mode == "edit" and is_cron_task)
    is_rescheduled = task.get("state") == "rescheduled"

    if show_temp_checkbox:
        head_col1, head_col2 = st.columns([1.8, 1], vertical_alignment="bottom")
        with head_col1:
            st.markdown(f"### {title_text}")
        with head_col2:
            default_temp_value = True if is_rescheduled else task.get("temporary", False)
            t_temp = st.checkbox(
                "Temporary Task (Delete after execution)", 
                value=default_temp_value, 
                disabled=is_rescheduled
            )
    else:
        st.markdown(f"### {title_text}")
        t_temp = False

    end_date_str = None
    if show_temp_checkbox and t_temp:
        init_end_date = datetime.today().date() + timedelta(days=1)
        if task.get("end_date"):
            try:
                date_part = str(task.get("end_date")).split("T")[0]
                init_end_date = datetime.strptime(date_part, "%Y-%m-%d").date()
            except:
                pass
                
        selected_date = st.date_input("End Date", value=init_end_date)
        end_date_str = f"{selected_date.isoformat()}T00:00:00"

    col1, col2 = st.columns(2)
    with col1:
        t_id = st.text_input("Task Unique ID", value=task.get("id", ""), disabled=(mode == "edit"))
        func_options = list(functions_data.keys())
        default_func_idx = 0
        if task and task.get("function") in func_options:
            default_func_idx = func_options.index(task.get("function"))
        t_func = st.selectbox("Target Function", options=func_options, index=default_func_idx)
        t_desc = st.text_area("Description / Role", value=task.get("description", ""))
    with col2:
        trigger_opts = ["cron", "date"]
        default_trig_idx = 0
        if task and task.get("trigger_type") in trigger_opts:
            default_trig_idx = trigger_opts.index(task.get("trigger_type"))
        t_trigger = st.selectbox("Trigger Type", options=trigger_opts, index=default_trig_idx, disabled=(mode == "edit"))

    st.markdown("---")
    
    if t_trigger == "cron":
        st.markdown("**Cron Parameters (APScheduler)**")
        c_cron = task.get("cron") if task else {}
        cc1, cc2, cc3 = st.columns(3)
        with cc1: c_min = st.text_input("Minute", value=c_cron.get("minute", "0"))
        with cc2: c_hour = st.text_input("Hour", value=c_cron.get("hour", "0"))
        with cc3: c_dow = st.text_input("Day of Week", value=c_cron.get("day_of_week", "*"))
        c_day = "*"
        c_month = "*"

    else:
        st.markdown("**Single Execution Parameters**")
        task = next((t for t in tasks_data if t['id'] == st.session_state.selected_task_id), None)
        
        init_val = ""
        if mode == "edit" and task and ("date" in task or "cron" not in task or "run_date" in task):
            task_date_raw = task.get("date", task.get("run_date", ""))
            if len(str(task_date_raw).split("-")) >= 5:
                try:
                    parts = str(task_date_raw).split("-")
                    init_val = f"{parts[0]}-{parts[1]}-{parts[2]}T{parts[3]}:{parts[4]}"
                except:
                    init_val = ""
            elif "T" in str(task_date_raw):
                init_val = str(task_date_raw)[:16]
                
        if not init_val:
            init_val = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%dT00:00")

        session_date_key = f"date_picker_val_{st.session_state.selected_task_id or 'new'}"
        if session_date_key not in st.session_state:
            st.session_state[session_date_key] = init_val

        field_id = f"datetime_input_{st.session_state.selected_task_id or 'new'}"
        val_saisie = st.text_input(
            "Date and Time", 
            value=st.session_state[session_date_key],
            key=field_id
        )
        st.session_state[session_date_key] = val_saisie

        st.components.v1.html(f"""
        <script>
            const inputs = window.parent.document.querySelectorAll('input');
            for (let input of inputs) {{
                if (input.value === "{val_saisie}") {{
                    input.type = 'datetime-local';
                    input.style.color = 'white';
                    break;
                }}
            }}
        </script>
        """, height=0)

        val_brute = st.session_state[session_date_key]
        if val_brute and len(str(val_brute)) >= 16:
            date_res_val = f"{str(val_brute)[:16]}:00"
        else:
            date_res_val = f"{init_val[:16]}:00"

    st.markdown("---")
    st.markdown("**Function Arguments**")
    
    args_list = []
    if t_func in functions_data:
        func_meta = functions_data[t_func]
        meta_args = func_meta.get("args", [])
        
        if meta_args:
            for idx, arg_meta in enumerate(meta_args):
                arg_name = arg_meta.get("name")
                default_val = ""
                if task and task.get("args") and idx < len(task["args"]):
                    default_val = str(task["args"][idx])
                elif "example" in arg_meta:
                    default_val = str(arg_meta["example"]).strip("'\"")
                    
                val = st.text_input(f"Argument: {arg_name}", value=default_val, key=f"arg_input_{idx}")
                args_list.append(val)
        else:
            st.info("This function takes no required arguments.")

    st.markdown("<br>", unsafe_allow_html=True)
    
    if is_rescheduled:
        b_cols = st.columns([1.2, 1, 4])
    else:
        b_cols = st.columns([1, 5])
        
    with b_cols[0]:
        if st.button("Save", type="primary", use_container_width=True):
            if not t_id.strip():
                st.error("ID is required.")
                return
            
            if mode == "edit" and show_temp_checkbox and t_temp and end_date_str:
                res_data = {
                    "new_cron_params": {
                        "minute": c_min,
                        "hour": c_hour,
                        "day_of_week": c_dow
                    },
                    "end_date": end_date_str
                }
                try:
                    response = requests.post(f"{API_URL}/tasks/{task_id}/reschedule", json=res_data)
                    if response.status_code == 200:
                        st.session_state.show_modal = False
                        st.session_state.modal_mode = None
                        st.session_state.selected_task_id = None
                        st.rerun()
                    else:
                        st.error(f"API Error (Reschedule): {response.text}")
                    return
                except Exception as e:
                    st.error(f"Communication error with API: {e}")
                    return
                
            new_t = {
                "id": t_id.strip(),
                "function": t_func,
                "description": t_desc,
                "trigger_type": t_trigger,
                "temporary": t_temp,
                "cron": None,
                "date": None,
                "args": args_list,
                "state": task.get("state", "active") if task else "active",
                "status": task.get("status", "active") if task else "active",
                "skip_next": task.get("skip_next", []) if task else []
            }
            
            if t_trigger == "cron":
                new_t["cron"] = {
                    "minute": c_min,
                    "hour": c_hour,
                    "day": c_day,
                    "month": c_month,
                    "day_of_week": c_dow
                }
            else:
                new_t["date"] = date_res_val
                new_t["run_date"] = date_res_val

            try:
                if mode == "add":
                    response = requests.post(f"{API_URL}/tasks", json=new_t)
                else:
                    response = requests.put(f"{API_URL}/tasks/{task_id}", json=new_t)
                
                if response.status_code == 200:
                    st.session_state.show_modal = False
                    st.session_state.modal_mode = None
                    st.session_state.selected_task_id = None
                    st.rerun()
                else:
                    st.error(f"API Error: {response.text}")
            except Exception as e:
                st.error(f"Communication error with API: {e}")

    if is_rescheduled:
        with b_cols[1]:
            if st.button("Reset", use_container_width=True):
                try:
                    response = requests.post(f"{API_URL}/tasks/{task_id}/reset-reschedule")
                    if response.status_code == 200:
                        st.session_state.show_modal = False
                        st.session_state.modal_mode = None
                        st.session_state.selected_task_id = None
                        st.rerun()
                    else:
                        st.error(f"Error during reset: {response.text}")
                except Exception as e:
                    st.error(f"Communication error with API: {e}")
        
        with b_cols[2]:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_modal = False
                st.session_state.modal_mode = None
                st.session_state.selected_task_id = None
                st.rerun()
    else:
        with b_cols[1]:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_modal = False
                st.session_state.modal_mode = None
                st.session_state.selected_task_id = None
                st.rerun()


col1, col2, col3 = st.columns([4.5, 1.5, 1.2], vertical_alignment="center")

with col1:
    st.markdown('<div style="display: flex; align-items: center; height: 40px;"><h1 style="font-size: 2.5rem; font-weight: bold; margin: 0; padding: 0; line-height: 40px;">🎛️ Task Orchestrator</h1></div>', unsafe_allow_html=True)

with col2:
    new_days = st.number_input(
        " ", min_value=3, max_value=7, 
        value=st.session_state.days_to_show,
        label_visibility="collapsed"
    )
    if new_days != st.session_state.days_to_show:
        st.session_state.days_to_show = new_days
        try:
            requests.post(f"{API_URL}/config", json={"days_to_show": new_days})
            st.rerun()
        except:
            pass

with col3:
    if st.button("➕ Add", type="primary", use_container_width=True):
        st.session_state.modal_mode = "add"
        st.session_state.show_modal = True
        st.rerun()

st.markdown("<hr style='margin: 0.2rem 0; border-color: #21262d;'>", unsafe_allow_html=True)

tab_cal, tab_list = st.tabs(["📅 Calendar", "📋 List"])

with tab_cal:
    today = datetime.now().date()
    num_days = st.session_state.days_to_show
    calendar_days = [
        {"label": (today + timedelta(days=i)).strftime("%A %d/%m"), "date_obj": today + timedelta(days=i)}
        for i in range(num_days)
    ]
    
    if tasks_data:
        with st.container(height=1000, border=False):
            cols = st.columns(num_days)
            for idx, day in enumerate(calendar_days):
                with cols[idx]:
                    st.markdown(f'<div class="day-header">{day["label"]}</div>', unsafe_allow_html=True)
                    todays_tasks = [t for t in tasks_data if is_task_on_day(t, day["date_obj"])]
                    todays_tasks = sorted(todays_tasks, key=get_task_sort_key)
                    
                    for t_idx, task in enumerate(todays_tasks):
                        state_str = task.get('state', 'active')
                        status_str = task.get('status', 'active')
                        is_paused = (state_str == 'paused')
                        
                        if "cron" in task and task["cron"]:
                            h = task['cron'].get('hour', '00')
                            m = task['cron'].get('minute', '00')
                            dow = task['cron'].get('day_of_week', '*')
                            
                            heure_run = f"{h}h{m}"
                            if dow != "*":
                                heure_run += f" (J: {dow})"
                        else:
                            try: 
                                heure_run = datetime.fromisoformat(task.get("date", task.get("run_date", ""))).strftime("%H:%M")
                            except: 
                                heure_run = "--:--"

                        if status_str == "err":
                            css_state = "err"
                        elif status_str in ["pause", "paused"]:
                            css_state = "paused"
                        elif state_str == "rescheduled":
                            css_state = "rescheduled"
                        else:
                            css_state = "active"
                        
                        with st.container(border=True):
                            full_func = task.get('function', '.')
                            module_name, func_name = full_func.split('.', 1) if '.' in full_func else (full_func, '')

                            desc_text = task.get('description', '')
                            display_desc = desc_text if desc_text.strip() else "&nbsp;"

                            st.markdown(f"""
                            <div class="task-card-wrapper" data-state="{css_state}">
                                <div class="card-status">{status_str.upper()}</div>
                                <div class="card-id" title="{task['id']}">{task['id']}</div>
                                <div class="card-line">⚙️ {func_name}()</div>
                                <div class="card-line">🕒 {heure_run}</div>
                                <div class="card-desc">{display_desc}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            b_col1, b_col2, b_col3, b_col4 = st.columns(4)
                            
                            with b_col1:
                                is_paused = (task.get("status", "active") == "pause")
                                icon = "▶️" if is_paused else "⏸️"
                                if st.button(icon, key=f"p_{day['label']}_{task['id']}_{t_idx}"):
                                    endpoint = "resume" if is_paused else "pause"
                                    requests.post(f"{API_URL}/tasks/{task['id']}/{endpoint}")
                                    st.rerun()

                            with b_col2:
                                skip_target = get_global_skip_index(task['id'], day["date_obj"], tasks_data)
                                if st.button("⏭️", key=f"s_{day['label']}_{task['id']}_{t_idx}"):
                                    response = requests.post(f"{API_URL}/tasks/{task['id']}/skip/{skip_target}")
                                    if response.status_code == 200:
                                        st.toast(f"Skip {skip_target} sent for {task['id']}")
                                        st.rerun()
                                    else:
                                        st.error(f"Error {response.status_code}")

                            with b_col3:
                                if st.button("📝", key=f"edit_{task['id']}_{day['label']}"):
                                    st.session_state.modal_mode = "edit"
                                    st.session_state.selected_task_id = task['id']
                                    st.session_state.show_modal = True
                                    st.rerun()

                            with b_col4:
                                if st.button("🗑️", key=f"d_{day['label']}_{task['id']}_{t_idx}"):
                                    requests.delete(f"{API_URL}/tasks/{task['id']}")
                                    st.rerun()


with tab_list:
    h1, h2, h3, h4, h5 = st.columns([2, 2, 3, 1, 2])
    with h1: st.markdown("**Task ID**")
    with h2: st.markdown("**Trigger / Schedule**")
    with h3: st.markdown("**Arguments**")
    with h4: st.markdown("**Status**")
    with h5:
        if st.button("➕ Add Task", type="primary", use_container_width=True, key="list_add_task_btn"):
            st.session_state.modal_mode = "add"
            st.session_state.selected_task_id = None
            render_task_modal()
            
    st.markdown("---")
    
    if not tasks_data:
        st.info("No configured tasks.")
        
    for idx, task in enumerate(tasks_data):
        row1, row2, row3, row4, row5 = st.columns([2, 2, 3, 1, 2])
        with row1:
            st.markdown(f"**`{task['id']}`**")
        with row2:
            if task.get("trigger_type") == "cron":
                st.markdown(f"🤖 **Cron**: `{get_cron_description(task.get('cron'))}`")
            else:
                date_str = str(task.get("run_date", ""))
                st.markdown(f"📅 **Unique**: `{date_str[:16] if date_str else 'N/A'}`")
        with row3:
            if task.get("args"):
                st.markdown(f"`{task['args']}`")
            else:
                st.markdown("<span style='color:#484f58;'>None</span>", unsafe_allow_html=True)
        with row4:
            status = task.get("state", "ok")
            dot_color = "#56d364" if status in ["ok", "active"] else "#ffa23e"
            st.markdown(f"<span style='color:{dot_color};'>●</span> {status.capitalize()}", unsafe_allow_html=True)
        
        with row5:
            act_col1, act_col2, act_col3 = st.columns(3)
            
            with act_col1:
                is_paused = (task.get("status", "active") == "pause")
                p_label = "▶️" if is_paused else "⏸️"
                if st.button(p_label, key=f"p_{task['id']}_{idx}"):
                    endpoint = "resume" if is_paused else "pause"
                    requests.post(f"{API_URL}/tasks/{task['id']}/{endpoint}")
                    st.rerun()

            with act_col2:
                if st.button("📝", key=f"e_{task['id']}_{idx}"):
                    st.session_state.modal_mode = "edit"
                    st.session_state.selected_task_id = task['id']
                    st.session_state.show_modal = True
                    st.rerun()

            with act_col3:
                if st.button("🗑️", key=f"d_{task['id']}_{idx}"):
                    requests.delete(f"{API_URL}/tasks/{task['id']}")
                    st.rerun()
        st.markdown("<hr style='margin: 0.5rem 0; border-color: #21262d;'>", unsafe_allow_html=True)

if st.session_state.show_modal:
    render_task_modal()

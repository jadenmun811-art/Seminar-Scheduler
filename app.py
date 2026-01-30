import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import re
import json
import os
import asyncio
import edge_tts
import pytz
import streamlit.components.v1 as components
import time

# ==========================================
# 1. 기본 설정 & CSS
# ==========================================
st.set_page_config(layout="wide", page_title="Seminar Schedule (Web) 🐾")

KST = pytz.timezone('Asia/Seoul')

# [핵심] 현재 시간 계산 (Python 내부용)
now_init = datetime.datetime.now(KST)
wkdays = ["월", "화", "수", "목", "금", "토", "일"]
init_time_str = f"{now_init.month}월 {now_init.day}일 {wkdays[now_init.weekday()]}요일 {now_init.strftime('%H:%M:%S')}"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Do+Hyeon&display=swap');

    .stApp {{
        background-color: #1E1E1E !important;
        color: white !important;
    }}

    section[data-testid="stSidebar"] {{
        background-color: #1E1E1E !important;
        border-right: 2px solid #333333;
    }}
    section[data-testid="stSidebar"] * {{
        color: white !important;
    }}

    textarea {{
        background-color: #333333 !important;
        color: white !important;
        border: 1px solid #555 !important;
    }}
    
    .streamlit-expanderHeader {{
        background-color: #333333 !important;
        color: white !important;
    }}
    div[data-testid="stExpanderDetails"] {{
        background-color: #2C2C2C !important;
    }}

    html, body, [class*="css"] {{
        font-family: 'Do Hyeon', sans-serif !important;
    }}

    .header-container {{
        display: flex; justify-content: center; align-items: center; gap: 20px; 
        padding: 1.5rem 0; margin-bottom: 2rem; 
        background-color: #2C2C2C; 
        border-bottom: 4px solid #555; 
        border-radius: 15px;
    }}
    .main-title {{ 
        font-size: 3rem; color: #FFFFFF; margin: 0; text-shadow: 2px 2px 0px #000000;
    }}
    /* 시계용 ID 부여 */
    .live-clock {{ 
        font-size: 2rem; color: #FFFFFF; background: #333;
        padding: 5px 15px; border: 2px solid #777; border-radius: 15px;
    }} 

    div.stButton > button {{
        background-color: #FF6E56 !important;
        color: white !important;
        font-family: 'Do Hyeon', sans-serif !important;
        font-size: 24px !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 10px 20px !important;
        box-shadow: 0px 4px 0px #C94530 !important;
        transition: all 0.1s;
        width: 100%;
    }}
    div.stButton > button:active {{
        transform: translateY(4px); box-shadow: 0px 0px 0px #C94530 !important;
    }}

    .stMarkdown, .stText, h1, h2, h3, p {{ color: white !important; }}
    .block-container {{ padding-top: 2rem; }}
    
    /* [숨김 버튼] 자동 새로고침 트리거용 버튼 숨기기 */
    .refresh-btn-hidden {{
        display: none;
    }}
    </style>
    
    <div class="header-container">
        <div class="main-title">✨ SEMINAR SCHEDULE</div>
        <div class="live-clock"><span id="clock-target">{init_time_str}</span></div>
    </div>
    """,
    unsafe_allow_html=True
)

# ==========================================
# 2. TTS 생성 및 보관함
# ==========================================
async def generate_tts_audio(text, filename="status_alert.mp3"):
    try:
        communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
        await communicate.save(filename)
    except: pass

HISTORY_FILE = "schedule_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_to_history(text):
    history = load_history()
    first_line = text.split('\n')[0].strip()
    match = re.search(r'(\d{1,2})\.(\d{1,2})\s*\(([월화수목금토일])\)', first_line)
    if match: title = f"{match.group(1)}월 {match.group(2)}일 {match.group(3)}요일"
    else: title = f"{first_line[:20]}... ({datetime.datetime.now(KST).strftime('%H:%M')})"
    history[title] = text
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def delete_history(key):
    history = load_history()
    if key in history:
        del history[key]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

def set_input_text(text):
    st.session_state['input_text'] = text

# ==========================================
# 3. 데이터 파싱
# ==========================================
def parse_time_str(time_str):
    try:
        time_str = time_str.replace(" ", "")
        match = re.search(r'(\d{1,2})시(?:(\d{1,2})분)?', time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return datetime.time(hour, minute)
    except: return None
    return None

COLORS = {
    "BLUE_MAIN": "#5E7CE2", "BLUE_SETUP": "#AAB8E8",  
    "ORANGE_MAIN": "#E6A85E", "ORANGE_SETUP": "#F2D1A8", 
    "GREEN_MAIN": "#76C48C", "GREEN_SETUP": "#B5E2C1", 
    "GRAY_MAIN": "#9E9E9E", "GRAY_SETUP": "#E0E0E0"
}
PAST_COLOR = "#4A4A4A" 

def shorten_location(loc_name):
    match = re.search(r'(\d+)\s*([가-힣])', loc_name)
    if match: return f"{match.group(1)}{match.group(2)}" 
    return loc_name[:2]

def get_color_for_location(loc_name, is_setup):
    if "소" in loc_name: return COLORS["BLUE_SETUP"] if is_setup else COLORS["BLUE_MAIN"]
    elif "세" in loc_name: return COLORS["ORANGE_SETUP"] if is_setup else COLORS["ORANGE_MAIN"]
    elif "간" in loc_name: return COLORS["GREEN_SETUP"] if is_setup else COLORS["GREEN_MAIN"]
    else: return COLORS["GRAY_SETUP"] if is_setup else COLORS["GRAY_MAIN"]

def extract_schedule(raw_text):
    schedule_data = []
    js_events = [] 
    today_kst = datetime.datetime.now(KST).date()
    sections = re.split(r'={5,}', raw_text)
    
    for section in sections:
        if not section.strip(): continue
        lines = [l.strip() for l in section.strip().split('\n') if l.strip()]
        data = { "date_obj": today_kst, "start": None, "setup": None, "end": None, "location": "미정", "staff": "", "office": "", "aide": "", "title": "", "simple_remark": "일반" }
        
        if len(lines) > 0:
            line1 = lines[0]
            date_match = re.search(r'(\d{1,2})\.(\d{1,2})', line1)
            if date_match: 
                try: data['date_obj'] = datetime.date(today_kst.year, int(date_match.group(1)), int(date_match.group(2)))
                except ValueError: data['date_obj'] = today_kst

            if '/' in line1:
                times_part = line1.split(')')[-1] if ')' in line1 else line1
                parts = times_part.split('/')
                data['start'] = parse_time_str(parts[0])
                if len(parts) > 1: data['setup'] = parse_time_str(parts[1])

        if len(lines) > 1:
            line2 = lines[1]
            if '-' in line2: parts = line2.split('-'); data['location'] = parts[0].strip(); data['staff'] = parts[1].strip()
            else: data['location'] = line2

        if len(lines) > 2:
            line3 = lines[2]
            if '/' in line3: parts = line3.split('/'); data['office'] = parts[0].strip(); data['aide'] = parts[1].strip()
            else: data['office'] = line3

        if len(lines) > 3: data['title'] = lines[3]
        if len(lines) > 4: 
            raw_broadcast = "\n".join(lines[4:])
            if "생중계" in raw_broadcast: data['simple_remark'] = "📡 생중계"
            elif "녹화" in raw_broadcast: data['simple_remark'] = "📹 녹화"
            else: data['simple_remark'] = "-"

        if data['start'] and data['setup']:
            try:
                start_dt = KST.localize(datetime.datetime.combine(data['date_obj'], data['start']))
                setup_dt = KST.localize(datetime.datetime.combine(data['date_obj'], data['setup']))
                end_dt = start_dt + datetime.timedelta(hours=2)
                
                setup_color = get_color_for_location(data['location'], is_setup=True)
                main_color = get_color_for_location(data['location'], is_setup=False)

                broadcast_style = "color: #D32F2F; font-weight: bold;" if "생중계" in data['simple_remark'] else "color: #388E3C; font-weight: bold;"
                
                desc = f"""<div style='text-align: left; font-family: "Do Hyeon", sans-serif; font-size: 20px; line-height: 1.6; color: #000000; background-color: #ffffff; padding: 10px; border-radius: 5px;'>
                    <span style='font-size: 22px; font-weight: bold; color: #FF007F;'>🐻 [{data['location']}]</span><br>
                    <span>♥ 의원실: {data['office']}</span><br>
                    <span>📝 제　목: {data['title']}</span><br>
                    <span>⏰ 시　간: {setup_dt.strftime('%H:%M')} (셋팅) ~ {start_dt.strftime('%H:%M')} (시작)</span><br>
                    <span>👤 담당자: {data['staff']}</span><br>
                    <span style='{broadcast_style}'>📺 방　송: {data['simple_remark']}</span></div>"""

                if "," in data['staff']: staff_display = data['staff'].replace(",", "<br>")
                else: staff_display = data['staff']

                schedule_data.append(dict(Task=data['location'], Start=setup_dt, Finish=start_dt, Resource="셋팅", Status="대기", ColorCode=setup_color, BarText="SET", Description=desc, Staff=staff_display))
                schedule_data.append(dict(Task=data['location'], Start=start_dt, Finish=end_dt, Resource="본행사", Status="대기", ColorCode=main_color, BarText=staff_display, Description=desc, Staff=staff_display))
                
                js_events.append({ "location": data['location'], "setup_ts": setup_dt.timestamp() * 1000, "staff": data['staff'] })
            except Exception: continue

    return schedule_data, js_events

def process_progressive_data(data):
    now = datetime.datetime.now(KST)
    processed = []
    
    for item in data:
        start = item['Start']
        finish = item['Finish']
        
        status = "대기"
        if finish <= now: status = "종료"
        elif start <= now < finish: 
            status = "ON AIR" if item['Resource'] == "본행사" else "셋팅중"
        elif item['Resource'] == "셋팅" and (start - datetime.timedelta(minutes=30)) <= now < start:
            status = "셋팅임박"
            
        item['Status'] = status 

        if finish <= now:
            item_copy = item.copy()
            item_copy['ColorCode'] = PAST_COLOR
            processed.append(item_copy)
        elif start >= now:
            item_copy = item.copy()
            item_copy['ColorCode'] = item['ColorCode']
            processed.append(item_copy)
        else:
            part_past = item.copy()
            part_past['Finish'] = now
            part_past['ColorCode'] = PAST_COLOR
            part_past['BarText'] = "" 
            processed.append(part_past)
            
            part_future = item.copy()
            part_future['Start'] = now
            part_future['ColorCode'] = item['ColorCode'] 
            processed.append(part_future)
            
    return processed

# ==========================================
# 4. 메인 화면 구성
# ==========================================
if 'input_text' not in st.session_state: st.session_state['input_text'] = ""

with st.sidebar:
    st.header("📝 스케줄 관리")
    tts_enabled = st.checkbox("🔊 TTS 소리 켜기 (체크 시 켜짐)", value=True)
    st.divider()

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("💾 보관함 저장"):
            if st.session_state['input_text'].strip(): save_to_history(st.session_state['input_text']); st.success("저장됨")
    with col2:
        if st.button("🗑️ 초기화"): st.session_state['input_text'] = ""; st.rerun()

    st.text_area("텍스트 붙여넣기", height=400, key="input_text")
    if st.button("🥕 스케줄 불러오기", type="primary"): st.rerun()

    st.divider()
    st.subheader("📂 보관함")
    history = load_history()
    for key in sorted(history.keys(), reverse=True):
        with st.expander(key):
            st.button("불러오기", key=f"load_{key}", on_click=set_input_text, args=(history[key],))
            if st.button("삭제", key=f"del_{key}"): delete_history(key); st.rerun()

# [핵심] 자동 새로고침용 숨겨진 버튼
# 이 버튼이 눌리면 Streamlit이 Rerun 됩니다. JS가 30초마다 이걸 누릅니다.
if st.button("Refresh Trigger", key="auto_refresh_btn", help="Hidden trigger"):
    pass # 그냥 리런만 시키면 됨

# CSS로 버튼 숨기기 (class name 이용)
st.markdown(
    """
    <style>
    div.stButton > button[kind="secondary"] {
        display: none; /* 화면에서 안 보이게 */
    }
    /* 하지만 Refresh Trigger는 key가 있어서 특정할 수 있음 */
    </style>
    """,
    unsafe_allow_html=True
)

raw_schedule_data, js_events = extract_schedule(st.session_state['input_text'])

if raw_schedule_data:
    processed_data = process_progressive_data(raw_schedule_data)
    df = pd.DataFrame(processed_data)
    
    task_map = {item['Task']: shorten_location(item['Task']) for item in raw_schedule_data}
    df['ShortTask'] = df['Task'].map(task_map)

    dynamic_height = max(800, len(task_map) * 80 + 250) 

    fig = px.timeline(
        df, x_start="Start", x_end="Finish", y="ShortTask", 
        text="BarText", custom_data=["Description"], 
        opacity=1.0 
    )
    
    fig.update_traces(
        marker_color=df['ColorCode'], 
        textposition='inside', insidetextanchor='middle', 
        hovertemplate="%{customdata[0]}<extra></extra>", 
        hoverlabel=dict(font_size=20, font_family="Do Hyeon", align="left", bgcolor="white", font_color="black"),
        textfont=dict(size=30, family="Do Hyeon", color="black"), 
        marker=dict(line=dict(width=0)) 
    )
    
    now_dt_kst = datetime.datetime.now(KST)
    half_window = datetime.timedelta(hours=4)
    range_x_start = now_dt_kst - half_window
    range_x_end = now_dt_kst + half_window

    fig.update_xaxes(
        showgrid=True, gridwidth=1, gridcolor='#444', 
        showline=False, ticks="", showticklabels=False, title="", 
        tickformat="%H:%M", dtick=3600000, 
        tickmode='linear', tickangle=0, side="top", 
        range=[range_x_start, range_x_end], automargin=True
    )
    
    fig.update_yaxes(
        showgrid=False, showline=False, showticklabels=False, 
        title="", autorange="reversed", automargin=True
    )
    
    start_hour = 5; end_hour = 21
    today_str = now_dt_kst.strftime("%Y-%m-%d")
    
    for hour in range(start_hour, end_hour + 1):
        time_str = f"{hour:02d}:00"
        x0_time = pd.Timestamp(f"{today_str} {hour:02d}:00")
        x1_time = pd.Timestamp(f"{today_str} {hour:02d}:59") if hour == end_hour else pd.Timestamp(f"{today_str} {hour+1:02d}:00")

        fig.add_shape(type="rect", xref="x", yref="paper", x0=x0_time, x1=x1_time, y0=1.01, y1=1.10, line=dict(color="white", width=1), fillcolor="#1E1E1E")
        fig.add_annotation(x=x0_time + (x1_time - x0_time) / 2, y=1.055, xref="x", yref="paper", text=time_str, showarrow=False, yanchor="middle", font=dict(size=26, color="white", family="Do Hyeon"))

    unique_tasks_ordered = []
    seen = set()
    for item in raw_schedule_data:
        t = item['Task']
        if t not in seen: unique_tasks_ordered.append(t); seen.add(t)

    for i, full_task_name in enumerate(unique_tasks_ordered):
        short_task = shorten_location(full_task_name)
        loc_main_color = get_color_for_location(full_task_name, is_setup=False)
        
        fig.add_shape(type="rect", xref="x", yref="y", x0=pd.Timestamp(f"{today_str} 05:00"), x1=pd.Timestamp(f"{today_str} 21:00"), y0=i-0.1, y1=i+0.1, fillcolor="#333333", line=dict(width=0), layer="below")
        fig.add_shape(type="rect", xref="paper", yref="y", x0=-0.07, x1=-0.06, y0=i-0.4, y1=i+0.4, fillcolor=loc_main_color, line=dict(width=0))
        fig.add_annotation(x=-0.02, xref="paper", y=i, yref="y", text=f"<b>{short_task}</b>", showarrow=False, font=dict(size=45, color="white", family="Do Hyeon"), align="right")
        
        items = [x for x in processed_data if x['Task'] == full_task_name]
        status_text = "⚪ 대기"; status_color = "gray"
        
        raw_items = [x for x in raw_schedule_data if x['Task'] == full_task_name]
        has_on_air = False; has_setting = False; has_imminent = False; all_finished = True
        
        for item in raw_items:
            start = item['Start']; finish = item['Finish']
            if finish > now_dt_kst: all_finished = False
            if start <= now_dt_kst < finish:
                if item['Resource'] == "본행사": has_on_air = True
                elif item['Resource'] == "셋팅": has_setting = True
            if item['Resource'] == "셋팅" and (start - datetime.timedelta(minutes=30)) <= now_dt_kst < start: has_imminent = True

        if has_on_air: status_text, status_color = "🔴 ON AIR", "#FF5252"
        elif has_setting: status_text, status_color = "🟡 셋팅중", "#FFD740"
        elif has_imminent: status_text, status_color = "🟠 셋팅임박", "#FFAB40"
        elif all_finished: status_text, status_color = "⚫ 종료", "#9E9E9E"
            
        fig.add_annotation(x=0.98, xref="paper", y=i, yref="y", text=status_text, showarrow=False, font=dict(size=24, color=status_color, family="Do Hyeon"), align="right", bgcolor="#1E1E1E", bordercolor=status_color, borderwidth=2, borderpad=4)

    fig.add_vline(x=now_dt_kst, line_width=2, line_dash="solid", line_color="red")
    fig.add_annotation(x=now_dt_kst, y=1.10, xref="x", yref="paper", text="▼", showarrow=False, font=dict(size=25, color="red"), yshift=0)

    fig.update_layout(height=dynamic_height, font=dict(size=14, family="Do Hyeon"), showlegend=False, paper_bgcolor='#1E1E1E', plot_bgcolor='#1E1E1E', margin=dict(t=120, b=100, l=180, r=10), hoverlabel_align='left')
    
    st.plotly_chart(fig, use_container_width=True, config={'responsive': True})
else:
    st.info("👈 왼쪽 사이드바에 스케줄을 입력하고 '🥕 스케줄 불러오기'를 누르세요.")

js_events_json = json.dumps(js_events)
js_tts_enabled = str(tts_enabled).lower()

components.html(
    f"""
    <script>
        const events = {js_events_json};
        const announced = new Set(); 
        const ttsEnabled = {js_tts_enabled};
        let timeSinceLastReload = 0; 

        // 1초마다 실행되는 메인 루프 (시계 + TTS + 리프레시)
        function updateSystem() {{
            const now = new Date();
            timeSinceLastReload += 1000;
            
            // 1. 시계 업데이트 (Clock Update)
            // Python에서 만든 span 태그(clock-target)를 찾아서 내용물 교체
            const clockTarget = window.parent.document.getElementById('clock-target');
            if (clockTarget) {{
                const timeString = now.toLocaleTimeString('ko-KR', {{ hour12: false }});
                const dateString = now.toLocaleDateString('ko-KR', {{ month: 'long', day: 'numeric', weekday: 'long' }});
                clockTarget.innerText = dateString + " " + timeString;
            }}

            // 2. TTS 알림 로직
            events.forEach(event => {{
                const setupTime = new Date(event.setup_ts);
                const diffMs = setupTime - now;
                const diffMins = diffMs / 1000 / 60; 

                if (diffMins >= 4.9 && diffMins <= 5.1) {{
                    const key = event.location + "_5min";
                    if (!announced.has(key)) {{ 
                        speak(event.location + ", 셋팅 시작 5분 전입니다. " + event.staff + " 준비해 주세요."); 
                        announced.add(key); 
                    }}
                }}
                if (diffMins >= -0.1 && diffMins <= 0.1) {{
                    const key = event.location + "_exact";
                    if (!announced.has(key)) {{ 
                        speak(event.location + ", 셋팅 시작 시간입니다. " + event.staff + " 준비해 주세요."); 
                        announced.add(key); 
                    }}
                }}
            }});

            // 3. 자동 새로고침 (Auto Refresh) - 30초마다
            if (timeSinceLastReload >= 30000) {{
                // Streamlit의 모든 버튼 중 'Refresh Trigger' 텍스트를 가진 버튼을 찾아서 클릭
                // 'auto_refresh_btn'은 실제 HTML에서 data-testid나 텍스트로 찾음
                const buttons = window.parent.document.querySelectorAll('button');
                for (const btn of buttons) {{
                    // 우리가 만든 숨겨진 버튼 찾기 (텍스트 내용이나 aria-label로 추정)
                    // 여기서는 단순히 가장 마지막에 추가된 버튼이거나 특정 속성을 가진 것을 찾기보다,
                    // 숨겨진 버튼이 클릭되면 리로드됨.
                    // 간단한 방식: 페이지 내에 Refresh Trigger라는 텍스트를 가진 버튼 찾기
                    if (btn.innerText.includes("Refresh Trigger")) {{
                        btn.click();
                        timeSinceLastReload = 0; 
                        break;
                    }}
                }}
            }}
        }}

        function speak(text) {{
            if (ttsEnabled && 'speechSynthesis' in window) {{
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'ko-KR'; utterance.rate = 1.0;     
                window.speechSynthesis.speak(utterance);
            }}
        }}

        setInterval(updateSystem, 1000);
    </script>
    """,
    height=0
)

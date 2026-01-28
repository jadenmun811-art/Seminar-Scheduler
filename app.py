import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import re
import json
import os
import asyncio
import edge_tts
import pytz # [필수] 한국 시간 처리를 위한 라이브러리

# ==========================================
# 1. 기본 설정 & CSS
# ==========================================
st.set_page_config(layout="wide", page_title="Seminar Schedule (Web) 🐾")

# [한국 시간 설정] 서버가 어디에 있든 한국 시간 기준
KST = pytz.timezone('Asia/Seoul')

# 상단 고정 바 & 스타일
st.markdown(
    """
    <style>
    .fixed-time-bar {
        position: fixed; top: 3rem; left: 0; width: 100%;
        background-color: #ffffff; color: #FF5722; text-align: center;
        padding: 0.5rem 0; font-size: 1.5rem; font-weight: bold;
        z-index: 99999; border-bottom: 2px solid #FF5722;
        box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
    }
    .block-container { padding-top: 5rem; }
    div.stButton > button { white-space: nowrap; width: 100%; }
    </style>
    """,
    unsafe_allow_html=True
)

# ==========================================
# 2. TTS 생성 및 재생 (시스템 시간 기준 JS 활용)
# ==========================================
# JS에서 처리하므로 파이썬 쪽 함수는 제거하거나 간소화해도 되지만, 
# 파일 생성 로직은 유지합니다.
async def generate_tts_audio(text, filename="status_alert.mp3"):
    try:
        communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
        await communicate.save(filename)
    except: pass

# ==========================================
# 3. 보관함 관리
# ==========================================
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
    
    # [수정] 저장 시간도 한국 시간으로
    now_kst = datetime.datetime.now(KST)
    
    if match:
        month = match.group(1)
        day = match.group(2)
        weekday = match.group(3)
        title = f"{month}월 {day}일 {weekday}요일"
    else:
        title = f"{first_line[:20]}... ({now_kst.strftime('%H:%M')})"
    
    history[title] = text
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def delete_history(key):
    history = load_history()
    if key in history:
        del history[key]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

# 콜백 함수 (불러오기 에러 방지)
def set_input_text(text):
    st.session_state['input_text'] = text

# ==========================================
# 4. 데이터 파싱 (★한국 시간 적용★)
# ==========================================
def parse_time_str(time_str):
    try:
        time_str = time_str.replace(" ", "")
        match = re.search(r'(\d{1,2})시(?:(\d{1,2})분)?', time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            return datetime.time(hour, minute)
    except: return None
    return None

def extract_schedule(raw_text):
    schedule_data = []
    js_events = [] 
    
    # [수정] 기준 날짜도 한국 시간 기준 오늘로 설정
    today_kst = datetime.datetime.now(KST).date()
    
    sections = re.split(r'={5,}', raw_text)
    
    for section in sections:
        if not section.strip(): continue
        lines = [l.strip() for l in section.strip().split('\n') if l.strip()]
        
        data = {
            "date_obj": today_kst, # 기본값 한국 오늘
            "start": None, "setup": None, "end": None,
            "location": "미정", "staff": "",
            "office": "", "aide": "", "title": "", "broadcast": "",
            "simple_remark": "일반", "status": "대기", "color": "#90CAF9"
        }
        
        if len(lines) > 0:
            line1 = lines[0]
            date_match = re.search(r'(\d{1,2})\.(\d{1,2})', line1)
            if date_match:
                # 연도는 현재 한국 시간 기준
                data['date_obj'] = datetime.date(today_kst.year, int(date_match.group(1)), int(date_match.group(2)))
            if '/' in line1:
                times_part = line1.split(')')[-1] if ')' in line1 else line1
                parts = times_part.split('/')
                data['start'] = parse_time_str(parts[0])
                data['setup'] = parse_time_str(parts[1])

        if len(lines) > 1:
            line2 = lines[1]
            if '-' in line2:
                parts = line2.split('-')
                data['location'] = parts[0].strip()
                data['staff'] = parts[1].strip()
            else: data['location'] = line2

        if len(lines) > 2:
            line3 = lines[2]
            if '/' in line3:
                parts = line3.split('/')
                data['office'] = parts[0].strip()
                data['aide'] = parts[1].strip()
            else: data['office'] = line3

        if len(lines) > 3: data['title'] = lines[3]
        if len(lines) > 4: 
            raw_broadcast = "\n".join(lines[4:])
            if "생중계" in raw_broadcast: data['simple_remark'] = "📡 생중계"
            elif "녹화" in raw_broadcast: data['simple_remark'] = "📹 녹화"
            else: data['simple_remark'] = "-"

        if data['start'] and data['setup']:
            # [핵심] 날짜 + 시간 결합 시 timezone 정보(KST)를 부여
            start_dt = KST.localize(datetime.datetime.combine(data['date_obj'], data['start']))
            setup_dt = KST.localize(datetime.datetime.combine(data['date_obj'], data['setup']))
            end_dt = start_dt + datetime.timedelta(hours=2)
            
            # [핵심] 현재 시간도 KST로 가져와서 비교
            now = datetime.datetime.now(KST)
            
            # 상태 판단 로직
            setup_status = "대기(셋팅)"; setup_color = "#B0BEC5"
            main_status = "대기(행사)"; main_color = "#90CAF9"
            
            if now >= end_dt:
                setup_status = main_status = "종료"
                setup_color = main_color = "#E0E0E0"
            elif start_dt <= now < end_dt:
                setup_status = "종료"; setup_color = "#E0E0E0"
                main_status = "ON AIR"; main_color = "#FF8A65"
            elif setup_dt <= now < start_dt:
                setup_status = "셋팅중"; setup_color = "#FFF176"
                main_status = "대기(행사)"; main_color = "#90CAF9"
            elif (setup_dt - datetime.timedelta(minutes=30)) <= now < setup_dt:
                setup_status = "셋팅임박"; setup_color = "#81C784"
            
            broadcast_style = "color: #D32F2F; font-weight: bold;" if "생중계" in data['simple_remark'] else "color: #333333;"
            desc = f"""<div style='text-align: left; font-family: "Malgun Gothic", sans-serif; font-size: 14px; line-height: 1.6;'>
                <span style='color: #E65100; font-size: 16px; font-weight: bold;'>🐻 [{data['location']}]</span><br>
                <span style='color: #333333;'>♥ 의원실: {data['office']}</span><br>
                <span style='color: #333333;'>📝 제　목: {data['title']}</span><br>
                <span style='color: #333333;'>⏰ 시　간: {setup_dt.strftime('%H:%M')} (셋팅) ~ {start_dt.strftime('%H:%M')} (시작)</span><br>
                <span style='color: #333333;'>👤 담당자: {data['staff']}</span><br>
                <span style='{broadcast_style}'>📺 방　송: {data['simple_remark']}</span></div>"""

            schedule_data.append(dict(Task=data['location'], Start=setup_dt, Finish=start_dt, Resource="셋팅", Status=setup_status, Color=setup_color, BarText="SET", Description=desc, Opacity=0.8))
            schedule_data.append(dict(Task=data['location'], Start=start_dt, Finish=end_dt, Resource="본행사", Status=main_status, Color=main_color, BarText=f"{data['office']} | {data['staff']}", Description=desc, Opacity=1.0))
            
            # JS로 넘길 데이터 (밀리초 단위 타임스탬프)
            js_events.append({
                "location": data['location'],
                "setup_ts": setup_dt.timestamp() * 1000 
            })

    return schedule_data, js_events

# ==========================================
# 5. 메인 화면 구성
# ==========================================
st.title("✨ SEMINAR ZOO SCHEDULE 🐾")

# 상단 시계 자리표시자 (JS가 채움)
st.markdown('<div class="fixed-time-bar" id="live-clock">🕒 시간 로딩중...</div>', unsafe_allow_html=True)

if 'input_text' not in st.session_state: st.session_state['input_text'] = ""

with st.sidebar:
    st.header("📝 스케줄 관리")
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("💾 보관함 저장"):
            if st.session_state['input_text'].strip():
                save_to_history(st.session_state['input_text'])
                st.success("저장됨")
    with col2:
        if st.button("🗑️ 초기화"):
            st.session_state['input_text'] = ""
            st.rerun()

    st.text_area("텍스트 붙여넣기", height=400, key="input_text")

    if st.button("🥕 스케줄 불러오기", type="primary"):
        st.rerun()

    st.divider()
    st.subheader("📂 보관함")
    history = load_history()
    for key in sorted(history.keys(), reverse=True):
        with st.expander(key):
            st.button("불러오기", key=f"load_{key}", on_click=set_input_text, args=(history[key],))
            if st.button("삭제", key=f"del_{key}"):
                delete_history(key)
                st.rerun()

timeline_data, js_events = extract_schedule(st.session_state['input_text'])

if timeline_data:
    df = pd.DataFrame(timeline_data)
    fig = px.timeline(
        df, x_start="Start", x_end="Finish", y="Task", color="Status", text="BarText", custom_data=["Description"], 
        color_discrete_map={"종료": "#E0E0E0", "ON AIR": "#FF8A65", "셋팅중": "#FFF176", "셋팅임박": "#81C784", "대기(행사)": "#90CAF9", "대기(셋팅)": "#B0BEC5"},
        opacity=0.9
    )
    fig.update_traces(textposition='inside', insidetextanchor='middle', hovertemplate="%{customdata[0]}<extra></extra>", hoverlabel=dict(bgcolor="white", font_size=14, font_family="Malgun Gothic", align="left"))
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#EEEEEE', title="", autorange="reversed", tickfont=dict(size=18, color="#333333", weight="bold"))
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#EEEEEE', title="", tickformat="%H:%M", dtick=1800000, side="top", tickfont=dict(size=14))
    fig.update_layout(height=800, font=dict(size=14), showlegend=True, margin=dict(t=50, b=50, l=100), hoverlabel_align='left')
    
    # [수정] 현재 시간 선도 KST 기준으로
    now_dt_kst = datetime.datetime.now(KST)
    fig.add_vline(x=now_dt_kst, line_width=2, line_dash="solid", line_color="red")
    
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("👈 왼쪽 사이드바에 스케줄을 입력하고 '🥕 스케줄 불러오기'를 누르세요.")

# ==========================================
# 6. JavaScript: 시계 & TTS & 자동 리로드(차트 갱신용)
# ==========================================
# [중요] 차트 색깔을 바꾸려면 결국 파이썬 코드가 다시 돌아야 합니다.
# 1분마다 페이지를 조용히 리로드해서 차트 상태를 갱신합니다.
# TTS는 JS가 1초마다 체크하므로 정확한 시간에 나옵니다.

js_events_json = json.dumps(js_events)

components.html(
    f"""
    <script>
        const events = {js_events_json};
        const announced = new Set(); 

        function updateSystem() {{
            const now = new Date();
            
            // 1. 상단 시계 업데이트
            const timeString = now.toLocaleTimeString('ko-KR', {{ hour12: false }});
            const dateString = now.toLocaleDateString('ko-KR', {{ month: 'long', day: 'numeric', weekday: 'long' }});
            const clockElement = window.parent.document.getElementById('live-clock');
            if (clockElement) {{
                clockElement.innerText = "🕒 " + dateString + " " + timeString;
            }}

            // 2. TTS 알림 체크 (시스템 시간 기준)
            events.forEach(event => {{
                const setupTime = new Date(event.setup_ts);
                const diffMs = setupTime - now;
                const diffMins = diffMs / 1000 / 60; 

                // 5분 전 알림 (4.9 ~ 5.1분)
                if (diffMins >= 4.9 && diffMins <= 5.1) {{
                    const key = event.location + "_5min";
                    if (!announced.has(key)) {{
                        speak(event.location + ", 셋팅 시작 5분 전입니다.");
                        announced.add(key);
                    }}
                }}

                // 정각 알림 (-0.1 ~ 0.1분)
                if (diffMins >= -0.1 && diffMins <= 0.1) {{
                    const key = event.location + "_exact";
                    if (!announced.has(key)) {{
                        speak(event.location + ", 셋팅 시작 시간입니다.");
                        announced.add(key);
                    }}
                }}
            }});
        }}

        function speak(text) {{
            if ('speechSynthesis' in window) {{
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'ko-KR'; 
                utterance.rate = 1.0;     
                window.speechSynthesis.speak(utterance);
            }}
        }}

        // 1초마다 시계 및 TTS 체크
        setInterval(updateSystem, 1000);

        // [핵심] 1분(60000ms)마다 페이지를 새로고침하여 '차트 색깔'을 갱신
        // TTS는 위에서 1초마다 체크하므로 놓치지 않음
        setTimeout(function() {{
            window.parent.document.querySelector(".stApp").dispatchEvent(new KeyboardEvent("keydown", {{key: "r", keyCode: 82, ctrlKey: false, shiftKey: false, altKey: false, metaKey: false, bubbles: true}})); 
            // 위 코드는 R키(Rerun)를 누르는 효과를 냅니다 (Streamlit Trick)
            // 안될 경우 아래 표준 리로드 사용
            // window.location.reload(); 
        }}, 60000);

    </script>
    """,
    height=0
)
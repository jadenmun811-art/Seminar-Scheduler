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

# ==========================================
# 1. 기본 설정 & CSS (나눔고딕 폰트 적용)
# ==========================================
st.set_page_config(layout="wide", page_title="Seminar Schedule (Web) 🐾")

KST = pytz.timezone('Asia/Seoul')

now_init = datetime.datetime.now(KST)
wkdays = ["월", "화", "수", "목", "금", "토", "일"]
init_time_str = f"🕒 {now_init.month}월 {now_init.day}일 {wkdays[now_init.weekday()]}요일 {now_init.strftime('%H:%M:%S')}"

st.markdown(
    f"""
    <style>
    /* 구글 웹폰트 (나눔고딕) 임포트 */
    @import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&display=swap');

    /* 전체 폰트 적용 */
    html, body, [class*="css"] {{
        font-family: 'Nanum Gothic', sans-serif !important;
    }}

    .header-container {{
        display: flex; justify-content: center; align-items: center; gap: 20px; 
        padding: 1rem 0; margin-bottom: 1rem; background-color: white; border-bottom: 3px solid #FEBD17;
    }}
    .main-title {{ font-size: 2.5rem; font-weight: 900; color: #333333; margin: 0; }}
    .live-clock {{ font-size: 1.8rem; font-weight: bold; color: #F94680; }} /* 핫핑크 시계 */

    @media only screen and (max-width: 768px) {{
        .header-container {{ flex-direction: column; gap: 5px; }}
        .main-title {{ font-size: 1.5rem; }}
        .live-clock {{ font-size: 1.2rem; }}
        .block-container {{ padding-top: 1rem; }}
    }}
    
    .block-container {{ padding-top: 2rem; }}
    div.stButton > button {{ white-space: nowrap; width: 100%; font-family: 'Nanum Gothic', sans-serif; }}
    </style>
    
    <div class="header-container">
        <div class="main-title">✨ SEMINAR SCHEDULE 🐾</div>
        <div class="live-clock" id="live-clock">{init_time_str}</div>
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
            return datetime.time(hour, minute)
    except: return None
    return None

# [수정] 색상 팔레트 (Tropical Splash)
# ON AIR: 노랑, 셋팅중/임박: 핫핑크, 대기(행사): 틸(청록), 대기(셋팅): 연분홍
COLOR_PALETTE = {
    "종료": "#E0E0E0",
    "ON AIR": "#FEBD17",      # Yellow/Orange (Warning/Active)
    "셋팅중": "#F94680",      # Hot Pink (Urgent)
    "셋팅임박": "#F94680",    # Hot Pink
    "대기(행사)": "#1BC0BA",  # Teal (Fresh)
    "대기(셋팅)": "#FDB8D9"   # Light Pink (Soft)
}

# [수정] 장소 이름 축약 함수 (예: 제1세미나실 -> 1세)
def shorten_location(loc_name):
    # 숫자와 그 뒤에 오는 첫 한글 글자를 찾음
    match = re.search(r'(\d+)\s*([가-힣])', loc_name)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    # 숫자가 없으면 앞 2글자만 (예: 본관 -> 본관, 대회의실 -> 대회)
    return loc_name[:2]

def extract_schedule(raw_text):
    schedule_data = []
    js_events = [] 
    today_kst = datetime.datetime.now(KST).date()
    sections = re.split(r'={5,}', raw_text)
    
    for section in sections:
        if not section.strip(): continue
        lines = [l.strip() for l in section.strip().split('\n') if l.strip()]
        data = { "date_obj": today_kst, "start": None, "setup": None, "end": None, "location": "미정", "staff": "", "office": "", "aide": "", "title": "", "simple_remark": "일반", "status": "대기", "color": "#90CAF9" }
        
        if len(lines) > 0:
            line1 = lines[0]
            date_match = re.search(r'(\d{1,2})\.(\d{1,2})', line1)
            if date_match: data['date_obj'] = datetime.date(today_kst.year, int(date_match.group(1)), int(date_match.group(2)))
            if '/' in line1:
                times_part = line1.split(')')[-1] if ')' in line1 else line1
                parts = times_part.split('/')
                data['start'] = parse_time_str(parts[0]); data['setup'] = parse_time_str(parts[1])

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
            start_dt = KST.localize(datetime.datetime.combine(data['date_obj'], data['start']))
            setup_dt = KST.localize(datetime.datetime.combine(data['date_obj'], data['setup']))
            end_dt = start_dt + datetime.timedelta(hours=2)
            now = datetime.datetime.now(KST)
            
            setup_status = "대기(셋팅)"; main_status = "대기(행사)";
            
            if now >= end_dt: setup_status = main_status = "종료";
            elif start_dt <= now < end_dt: setup_status = "종료"; main_status = "ON AIR";
            elif setup_dt <= now < start_dt: setup_status = "셋팅중"; main_status = "대기(행사)";
            elif (setup_dt - datetime.timedelta(minutes=30)) <= now < setup_dt: setup_status = "셋팅임박";
            
            setup_color = COLOR_PALETTE.get(setup_status, "#90CAF9")
            main_color = COLOR_PALETTE.get(main_status, "#90CAF9")

            broadcast_style = "color: #D32F2F; font-weight: bold;" if "생중계" in data['simple_remark'] else "color: #388E3C; font-weight: bold;"
            
            # 툴팁 내용
            desc = f"""<div style='text-align: left; font-family: "Nanum Gothic", sans-serif; font-size: 14px; line-height: 1.6;'>
                <span style='color: #FEBD17; font-size: 16px; font-weight: 800;'>🐻 [{data['location']}]</span><br>
                <span style='color: #333;'>♥ 의원실: {data['office']}</span><br>
                <span style='color: #333;'>📝 제　목: {data['title']}</span><br>
                <span style='color: #333;'>⏰ 시　간: {setup_dt.strftime('%H:%M')} (셋팅) ~ {start_dt.strftime('%H:%M')} (시작)</span><br>
                <span style='color: #333;'>👤 담당자: {data['staff']}</span><br>
                <span style='{broadcast_style}'>📺 방　송: {data['simple_remark']}</span></div>"""

            # [수정] 담당자 표시 로직: 쉼표(,)가 있으면 2명으로 간주하고 줄바꿈
            if "," in data['staff']:
                staff_display = data['staff'].replace(",", "<br>")
            else:
                staff_display = data['staff']

            schedule_data.append(dict(Task=data['location'], Start=setup_dt, Finish=start_dt, Resource="셋팅", Status=setup_status, Color=setup_color, BarText="SET", Description=desc, Opacity=0.9))
            schedule_data.append(dict(Task=data['location'], Start=start_dt, Finish=end_dt, Resource="본행사", Status=main_status, Color=main_color, 
                BarText=staff_display, # 담당자만 표시
                Description=desc, Opacity=1.0))
            
            js_events.append({ "location": data['location'], "setup_ts": setup_dt.timestamp() * 1000 })

    return schedule_data, js_events

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

timeline_data, js_events = extract_schedule(st.session_state['input_text'])

if timeline_data:
    df = pd.DataFrame(timeline_data)
    dynamic_height = max(800, len(df['Task'].unique()) * 80 + 200)

    fig = px.timeline(
        df, x_start="Start", x_end="Finish", y="Task", 
        color="Status", text="BarText", custom_data=["Description"], 
        color_discrete_map=COLOR_PALETTE,
        opacity=0.9
    )
    
    # [수정] 차트 바 디자인: 입체감(테두리), 글자 크기 키움
    fig.update_traces(
        textposition='inside', insidetextanchor='middle', 
        hovertemplate="%{customdata[0]}<extra></extra>", 
        hoverlabel=dict(font_size=14, font_family="Nanum Gothic", align="left"),
        textfont=dict(size=18, weight="bold", family="Nanum Gothic"), # 글자 키움
        marker=dict(line=dict(width=2, color='#333333')) # 입체감 테두리
    )
    
    # [수정] 시간 범위: 05:00 ~ 21:00
    today_str = datetime.datetime.now(KST).strftime("%Y-%m-%d")
    range_x_start = f"{today_str} 05:00"
    range_x_end = f"{today_str} 21:00"

    # [수정] X축: 시간 글씨 크기 20px로 확대
    fig.update_xaxes(
        showgrid=False, 
        showline=True, linewidth=2, linecolor='black', mirror=True, 
        ticks="inside", tickwidth=2, tickcolor='black', ticklen=10, 
        title="", 
        tickformat="%H:%M", 
        dtick=3600000, 
        tickmode='linear', tickangle=0, 
        side="top", 
        tickfont=dict(size=20, weight="800", family="Nanum Gothic", color="black"), # 글자 큼지막하게
        range=[range_x_start, range_x_end], automargin=True
    )
    
    fig.update_yaxes(
        showgrid=False, 
        showline=True, linewidth=2, linecolor='black', mirror=True,
        showticklabels=False, # 기본 글자 끄고 아래에서 큰 글자로 대체
        title="", 
        autorange="reversed", 
        automargin=True
    )
    
    # [수정] 좌측 장소 표기: 2글자로 큼지막하게, 박스/배경 없이 글자만
    unique_tasks = df['Task'].unique()
    for i, task in enumerate(unique_tasks):
        # 가로선 (Row Divider)
        fig.add_hline(y=i + 0.5, line_width=1, line_color="black")
        
        # 장소 이름 축약 (예: 제1세미나실 -> 1세)
        short_task = shorten_location(task)
        
        # 글자만 표시 (배경 X, 박스 X)
        fig.add_annotation(
            x=-0.01, xref="paper", y=i, yref="y",
            text=f"<b>{short_task}</b>", showarrow=False,
            font=dict(size=24, color="black", family="Nanum Gothic"), # 폰트 24px
            align="right"
        )

    fig.update_layout(
        height=dynamic_height, 
        font=dict(size=14, family="Nanum Gothic"), 
        showlegend=True,
        paper_bgcolor='white', 
        plot_bgcolor='white',    
        margin=dict(t=80, b=100, l=100, r=10), # l=100: 글자 공간
        hoverlabel_align='left',
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )
    
    now_dt_kst = datetime.datetime.now(KST)
    fig.add_vline(x=now_dt_kst, line_width=2, line_dash="solid", line_color="red")
    
    st.plotly_chart(fig, use_container_width=True, config={'responsive': True})
else:
    st.info("👈 왼쪽 사이드바에 스케줄을 입력하고 '🥕 스케줄 불러오기'를 누르세요.")

# ==========================================
# 5. JavaScript (기존 기능 유지)
# ==========================================
js_events_json = json.dumps(js_events)
js_tts_enabled = str(tts_enabled).lower()

components.html(
    f"""
    <script>
        const events = {js_events_json};
        const announced = new Set(); 
        const ttsEnabled = {js_tts_enabled};
        let timeSinceLastReload = 0; 

        function updateSystem() {{
            const now = new Date();
            timeSinceLastReload += 1000;
            
            const timeString = now.toLocaleTimeString('ko-KR', {{ hour12: false }});
            const dateString = now.toLocaleDateString('ko-KR', {{ month: 'long', day: 'numeric', weekday: 'long' }});
            const clockElement = window.parent.document.getElementById('live-clock');
            if (clockElement) {{ clockElement.innerText = dateString + " " + timeString; }}

            events.forEach(event => {{
                const setupTime = new Date(event.setup_ts);
                const diffMs = setupTime - now;
                const diffMins = diffMs / 1000 / 60; 

                if (diffMins >= 4.9 && diffMins <= 5.1) {{
                    const key = event.location + "_5min";
                    if (!announced.has(key)) {{ speak(event.location + ", 셋팅 시작 5분 전입니다."); announced.add(key); }}
                }}
                if (diffMins >= -0.1 && diffMins <= 0.1) {{
                    const key = event.location + "_exact";
                    if (!announced.has(key)) {{ speak(event.location + ", 셋팅 시작 시간입니다."); announced.add(key); }}
                }}
            }});

            if (timeSinceLastReload >= 60000) {{
                if (!window.speechSynthesis.speaking) {{
                    window.parent.document.querySelector(".stApp").dispatchEvent(new KeyboardEvent("keydown", {{key: "r", keyCode: 82, ctrlKey: false, shiftKey: false, altKey: false, metaKey: false, bubbles: true}})); 
                    timeSinceLastReload = 0;
                }} else {{
                    timeSinceLastReload = 55000; 
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

        updateSystem();
        setInterval(updateSystem, 1000);
    </script>
    """,
    height=0
)

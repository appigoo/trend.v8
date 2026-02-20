import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime

# --- 頁面配置 ---
st.set_page_config(page_title="Pro-Trade Monitor", layout="wide", initial_sidebar_state="expanded")

# 自定義 CSS 讓介面更緊湊
st.markdown("""
    <style>
    .main { padding-top: 1rem; }
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 核心邏輯函數 ---
def fetch_data(ticker, interval):
    try:
        # 抓取 3 天數據確保指標（如 RSI/EMA）計算有足夠的緩衝期
        data = yf.download(ticker, period="3d", interval=interval, progress=False)
        if data.empty: return None
        # 處理 MultiIndex 欄位問題
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except Exception as e:
        return None

def get_vix_status():
    vix = fetch_data("^VIX", "2m")
    if vix is None or len(vix) < 2: return 20.0, 0.0
    curr_v = float(vix['Close'].iloc[-1])
    v_chg = curr_v - float(vix['Close'].iloc[-2])
    return curr_v, v_chg

def analyze_stock(df, v_chg, ema_f, ema_s):
    if df is None or len(df) < 30: return None, None
    
    df = df.copy()
    # 1. 計算技術指標 (使用完整的歷史數據確保準確)
    df['EMA_F'] = ta.ema(df['Close'], length=ema_f)
    df['EMA_S'] = ta.ema(df['Close'], length=ema_s)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['Vol_MA'] = ta.sma(df['Volume'], length=10)
    
    # 2. 支撐壓力 (Pivot Points - Standard)
    last_row = df.iloc[-1]
    high, low, close = float(last_row['High']), float(last_row['Low']), float(last_row['Close'])
    pivot = (high + low + close) / 3
    res_1, sup_1 = (2 * pivot) - low, (2 * pivot) - high

    # 3. 趨勢與量能判斷
    vol_ratio = float(last_row['Volume'] / last_row['Vol_MA']) if last_row['Vol_MA'] != 0 else 1.0
    trend = " Bullish" if last_row['EMA_F'] > last_row['EMA_S'] else " Bearish"
    
    # 4. 警報訊號
    prev_row = df.iloc[-2]
    msg, level = "監控中", "success"
    if prev_row['EMA_F'] <= prev_row['EMA_S'] and last_row['EMA_F'] > last_row['EMA_S']:
        msg, level = "↗️ 黃金交叉", "error" # 用紅色強調買點
    elif prev_row['EMA_F'] >= prev_row['EMA_S'] and last_row['EMA_F'] < last_row['EMA_S']:
        msg, level = "↘️ 死亡交叉", "error"
    elif close >= res_1 * 0.998:
        msg, level = "🧱 接近壓力", "warning"

    info = {
        "price": close,
        "chg_pct": ((close - df['Open'].iloc[-1]) / df['Open'].iloc[-1]) * 100,
        "rsi": float(last_row['RSI']),
        "vol_ratio": vol_ratio,
        "trend": trend,
        "res": res_1, "sup": sup_1,
        "msg": msg, "level": level
    }
    return df, info

# --- 側邊欄配置 ---
st.sidebar.header("🛠️ 監控參數")
input_symbols = st.sidebar.text_input("股票代碼 (逗號分隔)", "AAPL, NVDA, TSLA, 2330.TW")
symbols = [s.strip().upper() for s in input_symbols.split(",")]
interval = st.sidebar.selectbox("K線週期", ("1m", "2m", "5m", "15m"), index=0)
ema_f_val = st.sidebar.slider("快速 EMA", 5, 20, 9)
ema_s_val = st.sidebar.slider("慢速 EMA", 21, 60, 21)
refresh_rate = st.sidebar.slider("自動刷新 (秒)", 30, 300, 60)

# --- 主介面 ---
st.title("🚀 專業實時量價監控")
placeholder = st.empty()

while True:
    with placeholder.container():
        # VIX 指數橫幅
        v_val, v_chg = get_vix_status()
        v_col1, v_col2 = st.columns([1, 3])
        v_col1.metric("VIX Index", f"{v_val:.2f}", f"{v_chg:.2f}", delta_color="inverse")
        v_col2.info(f"💡 系統提示: {'波動加劇，建議縮小部位' if v_chg > 0.2 else '市場穩定，適合技術面操作'} | 更新於: {datetime.now().strftime('%H:%M:%S')}")

        # 頂部狀態摘要
        st.subheader("🔔 即時訊號摘要")
        cols = st.columns(len(symbols))
        stock_cache = {}

        for idx, sym in enumerate(symbols):
            df_raw = fetch_data(sym, interval)
            df, info = analyze_stock(df_raw, v_chg, ema_f_val, ema_s_val)
            stock_cache[sym] = (df, info)
            
            with cols[idx]:
                if info:
                    if info['level'] == "error": st.error(f"**{sym}: {info['msg']}**")
                    elif info['level'] == "warning": st.warning(f"**{sym}: {info['msg']}**")
                    else: st.success(f"**{sym}: {info['msg']}**")
                    st.caption(f"Trend: {info['trend']} | Vol: x{info['vol_ratio']:.1f}")
                else:
                    st.write(f"⚠️ {sym} 無數據")

        st.divider()

        # 詳細圖表區 (只顯示最後 30 根)
        for sym in symbols:
            df, info = stock_cache[sym]
            if df is not None:
                # 關鍵操作：資料切片只取最後 30 根 K 線
                df_plot = df.tail(30)
                
                with st.expander(f"📊 {sym} 詳細走勢 (近 30 根 K 線)", expanded=True):
                    c1, c2 = st.columns([1, 4])
                    with c1:
                        st.metric("Price", f"{info['price']:.2f}", f"{info['chg_pct']:.2f}%")
                        st.write(f"RSI(14): `{info['rsi']:.1f}`")
                        st.write(f"壓力: `{info['res']:.2f}`")
                        st.write(f"支撐: `{info['sup']:.2f}`")
                    
                    with c2:
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                            row_heights=[0.7, 0.3], vertical_spacing=0.05)
                        
                        # K線圖
                        fig.add_trace(go.Candlestick(
                            x=df_plot.index, open=df_plot['Open'], high=df_plot['High'],
                            low=df_plot['Low'], close=df_plot['Close'], name="Price"
                        ), row=1, col=1)
                        
                        # EMA 均線
                        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA_F'], line=dict(color='orange', width=1), name="EMA-F"), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA_S'], line=dict(color='blue', width=1), name="EMA-S"), row=1, col=1)
                        
                        # 支撐壓力線 (虛線)
                        fig.add_hline(y=info['res'], line_dash="dash", line_color="rgba(255,0,0,0.4)", row=1, col=1)
                        fig.add_hline(y=info['sup'], line_dash="dash", line_color="rgba(0,255,0,0.4)", row=1, col=1)

                        # 成交量
                        v_colors = ['red' if df_plot['Close'].iloc[i] < df_plot['Open'].iloc[i] else 'green' for i in range(len(df_plot))]
                        fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=v_colors, name="Vol"), row=2, col=1)

                        fig.update_layout(height=400, margin=dict(t=0, b=0, l=0, r=0), xaxis_rangeslider_visible=False, showlegend=False)
                        fig.update_xaxes(tickformat="%H:%M") # 優化 X 軸時間顯示
                        
                        st.plotly_chart(fig, use_container_width=True)

    time.sleep(refresh_rate)
    st.rerun()

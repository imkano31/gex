import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm

# Cấu hình giao diện Web
st.set_page_config(page_title="GEX Terminal", page_icon="📊", layout="wide")
st.title("📊 GEX Intraday Terminal")

def black_scholes_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

# Ô nhập mã
symbol = st.text_input("Nhập mã (VD: QQQ, SPY, AAPL):", "QQQ").upper()

if st.button("Tạo Plan Đầu Ngày"):
    with st.spinner(f'Đang kéo dữ liệu {symbol} từ Wall Street...'):
        ticker = yf.Ticker(symbol)
        
        try:
            spot_price = ticker.fast_info['lastPrice']
        except:
            spot_price = ticker.history(period="1d")['Close'].iloc[-1]
            
        expirations = ticker.options
        if not expirations:
            st.error("Không tìm thấy dữ liệu Options!")
        else:
            target_exp = expirations[0] 
            opt_chain = ticker.option_chain(target_exp)
            calls, puts = opt_chain.calls.copy(), opt_chain.puts.copy()

            r, T = 0.045, 1 / 365
            calls['gamma'] = calls.apply(lambda row: black_scholes_gamma(spot_price, row['strike'], T, r, max(row['impliedVolatility'], 0.01)), axis=1)
            calls['gex'] = calls['openInterest'] * calls['gamma'] * 100 * spot_price / 1e6

            puts['gamma'] = puts.apply(lambda row: black_scholes_gamma(spot_price, row['strike'], T, r, max(row['impliedVolatility'], 0.01)), axis=1)
            puts['gex'] = puts['openInterest'] * puts['gamma'] * 100 * spot_price * -1 / 1e6

            call_wall = calls.loc[calls['gex'].idxmax()]['strike']
            put_wall = puts.loc[puts['gex'].idxmin()]['strike']

            df_calls = calls[['strike', 'gex']].rename(columns={'gex': 'call_gex'})
            df_puts = puts[['strike', 'gex']].rename(columns={'gex': 'put_gex'})
            merged = pd.merge(df_calls, df_puts, on='strike', how='outer').fillna(0)
            merged['net_gex'] = merged['call_gex'] + merged['put_gex']
            
            merged['dist'] = abs(merged['strike'] - spot_price)
            near_spot = merged.sort_values('dist').head(20).sort_values('strike')
            
            gamma_flip = spot_price
            for i in range(len(near_spot) - 1):
                if (near_spot.iloc[i]['net_gex'] * near_spot.iloc[i+1]['net_gex']) <= 0:
                    gamma_flip = (near_spot.iloc[i]['strike'] + near_spot.iloc[i+1]['strike']) / 2
                    break

            # HIỂN THỊ LÊN WEB
            st.success(f"Dữ liệu chốt tại kỳ hạn: {target_exp}")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Giá Spot (Close)", f"{spot_price:.2f}")
            col2.metric("Call Wall (Cản)", f"{call_wall:.2f}")
            col3.metric("Gamma Flip", f"{gamma_flip:.2f}")
            col4.metric("Put Wall (Hỗ trợ)", f"{put_wall:.2f}")

            st.divider()
            st.subheader("📝 Kịch Bản Intraday")
            st.info(f"**1. Neutral (Base Case):** Dao động tích lũy giữa {put_wall:.2f} và {call_wall:.2f}.")
            st.success(f"**2. Bull Branch:** Bứt phá & giữ vững trên {gamma_flip:.2f} -> Hướng về Call Wall {call_wall:.2f}.")
            st.error(f"**3. Bear Branch:** Mất mốc {gamma_flip:.2f} -> Trượt nhanh về Put Wall {put_wall:.2f}.")

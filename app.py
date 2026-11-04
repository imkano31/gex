import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
import plotly.graph_objects as go

st.set_page_config(page_title="GEX Terminal", page_icon="📊", layout="wide")
st.title("📊 GEX Intraday Terminal (Bao gồm NQ Futures)")

def black_scholes_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

symbol = st.text_input("Nhập mã cơ sở (Khuyên dùng: QQQ để tính cho NQ):", "QQQ").upper()

if st.button("Tạo Plan Đầu Ngày"):
    with st.spinner(f'Đang kéo dữ liệu {symbol} và NQ=F từ Wall Street...'):
        ticker = yf.Ticker(symbol)
        nq_ticker = yf.Ticker("NQ=F")
        
        try:
            spot_price = ticker.fast_info['lastPrice']
        except:
            spot_price = ticker.history(period="1d")['Close'].iloc[-1]
            
        try:
            nq_spot = nq_ticker.fast_info['lastPrice']
        except:
            nq_spot = nq_ticker.history(period="1d")['Close'].iloc[-1]
            
        ratio = nq_spot / spot_price
            
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

            # Lọc biên độ +/- 7%
            lower_bound = spot_price * 0.93
            upper_bound = spot_price * 1.07
            calls_near = calls[(calls['strike'] >= lower_bound) & (calls['strike'] <= upper_bound)]
            puts_near = puts[(puts['strike'] >= lower_bound) & (puts['strike'] <= upper_bound)]

            if not calls_near.empty and not puts_near.empty:
                call_wall = calls_near.loc[calls_near['gex'].idxmax()]['strike']
                put_wall = puts_near.loc[puts_near['gex'].idxmin()]['strike']
            else:
                call_wall = calls.loc[calls['gex'].idxmax()]['strike']
                put_wall = puts.loc[puts['gex'].idxmin()]['strike']

            df_calls = calls_near[['strike', 'gex']].rename(columns={'gex': 'call_gex'})
            df_puts = puts_near[['strike', 'gex']].rename(columns={'gex': 'put_gex'})
            merged = pd.merge(df_calls, df_puts, on='strike', how='outer').fillna(0)
            merged['net_gex'] = merged['call_gex'] + merged['put_gex']
            
            merged['dist'] = abs(merged['strike'] - spot_price)
            near_spot = merged.sort_values('dist').head(20).sort_values('strike')
            
            gamma_flip = spot_price
            for i in range(len(near_spot) - 1):
                if (near_spot.iloc[i]['net_gex'] * near_spot.iloc[i+1]['net_gex']) <= 0:
                    gamma_flip = (near_spot.iloc[i]['strike'] + near_spot.iloc[i+1]['strike']) / 2
                    break

            call_wall_nq = call_wall * ratio
            put_wall_nq = put_wall * ratio
            gamma_flip_nq = gamma_flip * ratio

            st.success(f"Dữ liệu chốt tại kỳ hạn: {target_exp} | Hệ số quy đổi Ratio: {ratio:.2f}")
            
            # --- VẼ BIỂU ĐỒ GEX PROFILE ---
            st.markdown("### 📈 Biểu đồ GEX Profile")
            fig = go.Figure()
            # Cột Call GEX (Màu xanh hướng lên)
            fig.add_trace(go.Bar(x=merged['strike'], y=merged['call_gex'], name='Call GEX', marker_color='#00ff00'))
            # Cột Put GEX (Màu đỏ/hồng hướng xuống)
            fig.add_trace(go.Bar(x=merged['strike'], y=merged['put_gex'], name='Put GEX', marker_color='#ff007f'))
            
            # Kẻ vạch Spot Price
            fig.add_vline(x=spot_price, line_dash="dash", line_color="white", annotation_text="Giá Spot Hiện Tại", annotation_position="top left")
            
            fig.update_layout(
                barmode='relative',
                template='plotly_dark',
                xaxis_title="Strike Price",
                yaxis_title="Gamma Exposure (Triệu USD)",
                hovermode="x unified",
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)
            # -------------------------------

            st.markdown("### 🎯 ĐỐI CHIẾU MỐC GEX: QQQ vs NQ FUTURES")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**MỐC GEX (LEVELS)**")
                st.info("Call Wall (Cản trên)")
                st.warning("Gamma Flip (Pivot)")
                st.error("Put Wall (Hỗ trợ dưới)")
                
            with col2:
                st.markdown(f"**{symbol} (Spot: {spot_price:.2f})**")
                st.info(f"**{call_wall:.2f}**")
                st.warning(f"**{gamma_flip:.2f}**")
                st.error(f"**{put_wall:.2f}**")
                
            with col3:
                st.markdown(f"**NQ FUTURES (Giá: {nq_spot:.2f})**")
                st.info(f"**{call_wall_nq:.2f}**")
                st.warning(f"**{gamma_flip_nq:.2f}**")
                st.error(f"**{put_wall_nq:.2f}**")

            st.divider()
            st.subheader("📝 Kịch Bản Trade Intraday cho NQ Futures")
            st.info(f"**1. Neutral (Base Case):** NQ đi ngang (ping-pong) trong biên độ {put_wall_nq:.2f} và {call_wall_nq:.2f}.")
            st.success(f"**2. Bull Branch:** NQ bứt phá & giữ vững trên mốc Pivot {gamma_flip_nq:.2f} -> Đánh Long nhắm tới {call_wall_nq:.2f}.")
            st.error(f"**3. Bear Branch:** NQ gãy mốc Pivot {gamma_flip_nq:.2f} -> Đánh Short ép giá về {put_wall_nq:.2f}.")

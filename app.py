import streamlit as st
import pandas as pd
import requests
import time
import io
from datetime import datetime

# 網頁基本設定
st.set_page_config(page_title="一手商品抓取工具", page_icon="📦")

st.title("📦 一手商品庫存抓取系統")
st.markdown("---")

# 側邊欄設定區
st.sidebar.header("📋 任務參數設定")
start_date = st.sidebar.date_input("開始日期", datetime(2025, 12, 29))
end_date = st.sidebar.date_input("結束日期", datetime(2025, 12, 29))
uploaded_file = st.sidebar.file_uploader("上傳供應商名單 (SHOP.xls)", type=["xls", "xlsx", "csv"])

# 爬蟲核心邏輯
class YishouWebScraper:
    def __init__(self, start_date, end_date):
        self.start_date = datetime.combine(start_date, datetime.min.time())
        self.end_date = datetime.combine(end_date, datetime.max.time())
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://servicewechat.com/wx6309080f/9129/page-frame.html",
            "xweb_xhr": "1",
            "Host": "api.yishouapp.com"
        }

    def get_valid_goods_ids(self, supplier_id):
        valid_ids = set()
        try: s_id_str = str(int(float(supplier_id)))
        except: return []
        page = 1
        while True:
            payload = {"supplier_id": s_id_str, "pageindex": str(page), "pagesize": "20", "version": "3.9.8", "plat_type": "wx", "sort": "5", "t_t": str(int(time.time() * 1000))}
            try:
                res = requests.post("https://api.yishouapp.com/supplier/supplier_detail_by_supplier_id", headers=self.headers, data=payload, timeout=10).json()
                goods = res.get("data", {}).get("goods", [])
                if not goods: break
                for g in goods:
                    sale_time = g.get("first_sale_time", "")
                    if not sale_time: continue
                    item_date = datetime.strptime(sale_time, "%Y%m%d")
                    if self.start_date <= item_date <= self.end_date:
                        valid_ids.add(str(g["goods_id"]))
                    elif item_date < self.start_date: return list(valid_ids)
                page += 1
                time.sleep(0.5)
            except: break
        return list(valid_ids)

    def get_sku_details(self, goods_id):
        payload = {"goods_id": str(goods_id), "version": "3.9.8", "plat_type": "wx"}
        try:
            res = requests.post("https://api.yishouapp.com/goods/get_goods_info_v2", headers=self.headers, data=payload, timeout=10).json()
            data = res.get("data", {})
            rows = []
            for attr in data.get("attribute", []):
                color = attr.get("color", "N/A")
                for item in attr.get("item", []):
                    stock_val = int(item.get('stock', 0))
                    if stock_val <= 1: continue 
                    rows.append({
                        "supplier_id": data.get("supplier_id", ""),
                        "goods_id": goods_id,
                        "first_sale_time": data.get("first_sale_time", ""),
                        "goods_name": data.get("goods_name", ""),
                        "sku": item.get("sku", "N/A"),
                        "color": color,
                        "size": item.get("size", "N/A"),
                        "stock": stock_val,
                        "shop_price": data.get("shop_price", "")
                    })
            return rows
        except: return []

# 網頁執行按鈕
if uploaded_file and st.sidebar.button("🚀 開始執行任務"):
    # 讀取檔案
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            try: df = pd.read_excel(uploaded_file)
            except: df = pd.read_csv(uploaded_file)
        s_ids = pd.to_numeric(df['supplier_id'], errors='coerce').dropna().unique()
    except Exception as e:
        st.error(f"讀取名單失敗: {e}")
        st.stop()

    scraper = YishouWebScraper(start_date, end_date)
    
    # 執行流程
    all_gids = set()
    status_bar = st.empty()
    status_bar.info("🔎 正在掃描供應商列表...")
    
    for i, sid in enumerate(s_ids):
        gids = scraper.get_valid_goods_ids(sid)
        all_gids.update(gids)
    
    if not all_gids:
        st.warning("⚠️ 區間內無商品。")
    else:
        st.success(f"✅ 發現 {len(all_gids)} 個新商品，開始抓取詳情...")
        final_data = []
        progress_bar = st.progress(0)
        
        for j, gid in enumerate(list(all_gids), 1):
            status_bar.text(f"正在抓取詳情: {gid} ({j}/{len(all_gids)})")
            details = scraper.get_sku_details(gid)
            if details: final_data.extend(details)
            progress_bar.progress(j / len(all_gids))
            time.sleep(5) # 安全冷卻
            
        if final_data:
            result_df = pd.DataFrame(final_data)
            st.dataframe(result_df)
            
            # 下載 CSV 按鈕
            csv = result_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 下載結果 CSV",
                data=csv,
                file_name=f"一手_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
            st.balloons()
        else:
            st.error("❌ 無符合庫存規則的商品。")

elif not uploaded_file:
    st.info("請在上傳檔案後點擊『開始執行任務』")
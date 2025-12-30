import streamlit as st
import pandas as pd
import requests
import time
import io
import base64
from datetime import datetime

# 網頁基本設定
st.set_page_config(page_title="一手商品庫存抓取工具", page_icon="📦")

st.title("📦 一手商品庫存抓取系統 (斷點續傳版)")
st.markdown("---")

# 初始化 Session State (用於斷線保全)
if 'collected_data' not in st.session_state:
    st.session_state.collected_data = [] # 儲存抓到的資料行
if 'processed_gids' not in st.session_state:
    st.session_state.processed_gids = set() # 儲存已完成的 ID

# 側邊欄設定區
st.sidebar.header("📋 任務參數設定")
start_date = st.sidebar.date_input("開始日期", datetime(2025, 12, 29))
end_date = st.sidebar.date_input("結束日期", datetime(2025, 12, 29))
uploaded_file = st.sidebar.file_uploader("上傳供應商名單 (SHOP.xls)", type=["xls", "xlsx", "csv"])

if st.sidebar.button("🗑️ 清空快取/重新開始"):
    st.session_state.collected_data = []
    st.session_state.processed_gids = set()
    st.rerun()

# 爬蟲核心邏輯
class YishouWebScraper:
    def __init__(self, start_date, end_date):
        self.start_datetime = datetime.combine(start_date, datetime.min.time())
        self.end_datetime = datetime.combine(end_date, datetime.max.time())
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://servicewechat.com/wx6309080f/9129/page-frame.html",
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
                res = requests.post("https://api.yishouapp.com/supplier/supplier_detail_by_supplier_id", headers=self.headers, data=payload, timeout=15).json()
                goods = res.get("data", {}).get("goods", [])
                if not goods: break
                for g in goods:
                    sale_time = g.get("first_sale_time", "")
                    if not sale_time: continue
                    item_date = datetime.strptime(sale_time, "%Y%m%d")
                    if self.start_datetime <= item_date <= self.end_datetime:
                        valid_ids.add(str(g["goods_id"]))
                    elif item_date < self.start_datetime: return list(valid_ids)
                page += 1
                time.sleep(0.3)
            except Exception as e:
                st.warning(f"掃描供應商 {supplier_id} 時發生網路抖動，嘗試跳過該頁。")
                break
        return list(valid_ids)

    def get_sku_details(self, goods_id):
        payload = {"goods_id": str(goods_id), "version": "3.9.8", "plat_type": "wx"}
        try:
            res = requests.post("https://api.yishouapp.com/goods/get_goods_info_v2", headers=self.headers, data=payload, timeout=15).json()
            data = res.get("data", {})
            main_img = data.get("goods_img", "")
            all_imgs = "|".join(data.get("imgs", []))
            
            rows = []
            for attr in data.get("attribute", []):
                color = attr.get("color", "N/A")
                for item in attr.get("item", []):
                    stock_val = int(item.get('stock', 0))
                    if stock_val <= 1: continue 
                    rows.append({
                        "provider_name": data.get("supplier_name", ""),
                        "brand_name": data.get("brand_name", ""),
                        "first_sale_time": data.get("first_sale_time", ""),
                        "goods_id": goods_id,
                        "goods_name": data.get("goods_name", ""),
                        "code": data.get("goods_sn", ""),
                        "goods_img": main_img,
                        "price": data.get("shop_price", ""),
                        "sku": item.get("sku", "N/A"),
                        "color": color,
                        "size": item.get("size", "N/A"),
                        "imgs": all_imgs
                    })
            return rows
        except Exception as e:
            return None # 回傳 None 代表失敗

# 自動下載函式
def f_auto_download(df):
    csv = df.to_csv(index=False, encoding='utf-8-sig')
    b64 = base64.b64encode(csv.encode('utf-8-sig')).decode()
    file_name = f"一手抓取_補抓版_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    js = f"""
    <a id="download_link" href="data:file/csv;base64,{b64}" download="{file_name}" style="display:none;">Download</a>
    <script>document.getElementById('download_link').click();</script>
    """
    st.components.v1.html(js, height=0)

# 執行邏輯
if uploaded_file and st.sidebar.button("🚀 開始執行(支援續傳)"):
    try:
        file_bytes = uploaded_file.read()
        try: df = pd.read_excel(io.BytesIO(file_bytes))
        except:
            try: df = pd.read_csv(io.BytesIO(file_bytes), encoding='utf-8-sig')
            except: df = pd.read_csv(io.BytesIO(file_bytes), encoding='cp950')
        df.columns = df.columns.astype(str).str.strip().str.lower()
        s_ids = pd.to_numeric(df['supplier_id'], errors='coerce').dropna().astype(int).unique()
    except Exception as e:
        st.error(f"檔案解析失敗: {e}"); st.stop()

    scraper = YishouWebScraper(start_date, end_date)
    status_bar = st.empty()
    
    # 第一步：掃描 ID
    all_gids = set()
    for i, sid in enumerate(s_ids):
        status_bar.info(f"🔎 正在掃描供應商列表... ({i+1}/{len(s_ids)})")
        all_gids.update(scraper.get_valid_goods_ids(sid))
    
    # 第二步：過濾掉「已經處理過」的 ID
    total_list = list(all_gids)
    remaining_list = [gid for gid in total_list if gid not in st.session_state.processed_gids]
    
    if not remaining_list:
        st.success("✨ 所有商品已處理完畢！")
    else:
        st.warning(f"📊 總共 {len(total_list)} 個商品，尚餘 {len(remaining_list)} 個待抓取。")
        progress_bar = st.progress(0)
        
        for j, gid in enumerate(remaining_list, 1):
            status_bar.text(f"正在抓取詳情: {gid} ({j}/{len(remaining_list)})")
            details = scraper.get_sku_details(gid)
            
            if details is not None:
                # 抓取成功：加入 Session 並記錄 ID
                st.session_state.collected_data.extend(details)
                st.session_state.processed_gids.add(gid)
            else:
                st.error(f"❌ 商品 {gid} 抓取超時，已跳過，稍後可重新執行續傳。")
            
            progress_bar.progress(j / len(remaining_list))
            time.sleep(5) # 5秒冷卻
            
    # 顯示目前已抓到的所有資料
    if st.session_state.collected_data:
        result_df = pd.DataFrame(st.session_state.collected_data)
        st.write(f"### 目前已累計資料：{len(result_df)} 筆")
        st.dataframe(result_df.head(50))
        
        # 下載按鈕
        csv_btn = result_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button("📥 下載目前已完成資料", csv_btn, file_name="一手斷點備份.csv", mime="text/csv")
        
        # 如果全部跑完，觸發自動下載
        if len(st.session_state.processed_gids) >= len(total_list):
            f_auto_download(result_df)
            st.balloons()
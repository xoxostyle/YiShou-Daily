import os
import time
import requests
import pandas as pd
from datetime import datetime

# --- 核心參數配置 ---
TOKEN = "8bfdd76c4f34df852be8c763dbbffd4a"
UDID = "7DBD18AA-1C43-44F8-8754-04D5D3DDDEF5"
UID = "19037923"
VERSION = "26.100000"
LIST_URL = "https://api.yishouapp.com/Supplier/supplier_detail_by_supplier_id"
DETAIL_URL = "https://api.yishouapp.com/goods/get_goods_info_ext"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "YiShou/7.64.01 (iPhone; iOS 26.1; Scale/3.00)"}

# 任務清單
today_str = datetime.now().strftime("%Y%m%d")
TASKS = [
    {"file": "SHOP3 - 1.xls", "start_date": "20250307"},
    {"file": "SHOP3 - 2.xls", "start_date": "20250307"},
    {"file": "SHOP4 - 1.xls", "start_date": "20250401"},
    {"file": "SHOP5 - 1.xls", "start_date": "20250501"},
    {"file": "SHOP5 - 2.xls", "start_date": "20250501"},
    {"file": "SHOP5 - 3.xls", "start_date": "20250901"},
]

def fetch_detail(gid, sid):
    body = {"goods_id": str(gid), "stall_id": str(sid), "token": TOKEN, "udid": UDID, "uid": UID, "version": VERSION, "plat_type": "iOS", "t_t": str(int(time.time()))}
    try:
        r = requests.post(DETAIL_URL, headers=HEADERS, data=body, timeout=20)
        data = r.json().get("data", {})
        imgs = [img.split('?')[0] for img in (data.get("detail_imgs") or data.get("desc_imgs") or []) if isinstance(img, str)]
        return {"price": data.get("exclusive_shop_price") or data.get("shop_price") or "", "imgs": ", ".join(imgs)}
    except: return {"price": "", "imgs": ""}

def run():
    os.makedirs("output_files", exist_ok=True)
    for task in TASKS:
        fname, s_date = task["file"], task["start_date"]
        print(f"處理中: {fname}...")
        try:
            df = pd.read_excel(fname)
            shop_map = {str(row[0]).strip(): str(row[1]).strip() for _, row in df.iterrows()}
            results = []
            for sid, sname in shop_map.items():
                list_body = {"supplier_id": sid, "page": 1, "token": TOKEN, "udid": UDID}
                res = requests.post(LIST_URL, headers=HEADERS, data=list_body).json()
                for g in res.get("data", {}).get("goods", []):
                    sale_t = str(g.get("first_sale_time", ""))
                    if s_date <= sale_t <= today_str:
                        d = fetch_detail(g.get("goods_id"), sid)
                        results.append({"provider_name": sname, "goods_id": g.get("goods_id"), "first_sale_time": sale_t, "price": d["price"], "imgs": d["imgs"]})
            if results: pd.DataFrame(results).to_csv(f"output_files/result_{fname.split('.')[0]}.csv", index=False, encoding="utf-8-sig")
        except Exception as e: print(f"失敗 {fname}: {e}")
        time.sleep(2)

if __name__ == "__main__": run()
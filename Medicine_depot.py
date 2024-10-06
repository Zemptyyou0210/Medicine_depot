import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import io
import cv2
from pyzbar import pyzbar
import time

# 設置頁面
st.set_page_config(page_title="藥品庫存管理系統", layout="wide")

# 創建 Google Drive API 客戶端
@st.cache_resource
def create_drive_client():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=credentials)

drive_service = create_drive_client()

def list_files_in_folder(folder_id):
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'",
        pageSize=1000,
        fields="nextPageToken, files(id, name)"
    ).execute()
    return results.get('files', [])

def read_excel_from_drive(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    file = io.BytesIO()
    downloader = MediaIoBaseDownload(file, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    file.seek(0)
    return pd.read_excel(file)

def read_from_drive():
    st.subheader("從 Google Drive 讀取資料")
    folder_id = "1LdDnfuu3N8v9PkePOhuJd0Ffv_FBQsMA"  # 直接使用固定的資料夾 ID
    
    files = list_files_in_folder(folder_id)
    if not files:
        st.warning("未找到 Excel 文件")
        if st.button("重新整理"):
            st.experimental_rerun()
        return None
    
    # 使用下拉式選單選擇 Excel 文件
    file_names = [file['name'] for file in files]
    if not file_names:
        st.warning("資料夾中沒有 Excel 文件")
        return None
    
    selected_file = st.selectbox("選擇 Excel 文件", file_names)
    
    if selected_file:
        file_id = next(file['id'] for file in files if file['name'] == selected_file)
        try:
            df = read_excel_from_drive(file_id)
            # 確保條碼列被正確讀取
            if '條碼' in df.columns:
                df['條碼'] = df['條碼'].astype(str).str.strip()
                df['條碼'] = df['條碼'].apply(lambda x: ''.join(filter(str.isdigit, x)))
            else:
                st.error("數據中缺少 '條碼' 列")
            
            # 添加 '檢貨狀態' 列
            if '檢貨狀態' not in df.columns:
                df['檢貨狀態'] = '未檢貨'
                st.info("已添加 '檢貨狀態' 列到數據中")

            st.session_state['inventory_df'] = df
            st.success(f"已成功讀取 {selected_file}")
            st.write(df)
        except Exception as e:
            st.error(f"讀取文件時發生錯誤: {str(e)}")
    else:
        st.warning("請選擇一個 Excel 文件")

# 新增的條碼掃描函數
def scan_barcodes():
    cap = cv2.VideoCapture(0)
    last_scan_time = 0
    scanned_barcodes = set()

    while True:
        ret, frame = cap.read()
        if not ret:
            st.error("無法讀取攝像頭")
            break

        barcodes = pyzbar.decode(frame)
        for barcode in barcodes:
            barcode_data = barcode.data.decode('utf-8')
            current_time = time.time()
            
            if current_time - last_scan_time > 2 and barcode_data not in scanned_barcodes:
                last_scan_time = current_time
                scanned_barcodes.add(barcode_data)
                yield barcode_data

        # 顯示攝像頭畫面
        st.image(frame, channels="BGR", use_column_width=True)

        # 檢查是否要停止掃描
        if st.button("停止掃描"):
            break

    cap.release()

def check_inventory():
    st.subheader("檢貨")
    
    if 'inventory_df' not in st.session_state:
        st.warning("請先從 Google Drive 讀取庫存文件")
        if st.button("前往讀取數據"):
            st.session_state.function_selection = "從 Google Drive 讀取"
            st.rerun()
        return

    df = st.session_state['inventory_df'].copy()
    
    # 顯示當前庫存狀態
    display_columns = ['藥庫位置', '藥品名稱', '盤撥量', '藥庫庫存', '檢貨狀態']
    df_display = df[display_columns]
    st.write("當前庫存狀態：")
    st.dataframe(df_display.style.applymap(
        lambda x: 'background-color: #90EE90' if x == '已檢貨' else 'background-color: #FFB6C1',
        subset=['檢貨狀態']
    ))

    if st.button("開始掃描"):
        for barcode in scan_barcodes():
            st.write(f"掃描到條碼: {barcode}")
            updated_df = check_and_mark_item(df, barcode)
            st.session_state['inventory_df'] = updated_df
            
            # 更新顯示
            df_display = updated_df[display_columns]
            st.dataframe(df_display.style.applymap(
                lambda x: 'background-color: #90EE90' if x == '已檢貨' else 'background-color: #FFB6C1',
                subset=['檢貨狀態']
            ))

    # 顯示檢貨進度
    total_items = len(df)
    checked_items = len(df[df['檢貨狀態'] == '已檢貨'])
    progress = checked_items / total_items
    st.progress(progress)
    st.write(f"檢貨進度：{checked_items}/{total_items} ({progress:.2%})")

def receive_inventory():
    st.subheader("收貨")
    
    if 'inventory_df' not in st.session_state:
        st.warning("請先從 Google Drive 讀取庫存文件")
        if st.button("前往讀取數據"):
            st.session_state.function_selection = "從 Google Drive 讀取"
            st.rerun()
        return

    df = st.session_state['inventory_df']
    
    # 只選擇需要的列
    display_columns = ['藥品名稱', '盤撥量', '收貨狀態']
    df_display = df[display_columns]

    # 顯示當前收貨狀態
    st.write("當前收貨狀態：")
    st.dataframe(df_display.style.applymap(
        lambda x: 'background-color: #90EE90' if x == '已收貨' else 'background-color: #FFB6C1',
        subset=['收貨狀態']
    ))

    # 使用 form 來確保條碼輸入後可以立即處理
    with st.form(key='barcode_form'):
        barcode = st.text_input("輸入商品條碼或掃描條碼", key="barcode_input")
        submit_button = st.form_submit_button("檢查商品")

    if submit_button or barcode:
        receive_item(df, barcode, display_columns)

    # 顯示收貨進度
    total_items = len(df)
    received_items = len(df[df['收貨狀態'] == '已收貨'])
    progress = received_items / total_items
    st.progress(progress)
    st.write(f"收貨進度：{received_items}/{total_items} ({progress:.2%})")

def receive_item(df, barcode, display_columns):
    if '條碼' not in df.columns:
        st.error("數據框中缺少 '條碼' 列")
        return
    
    item = df[df['條碼'] == barcode]
    if not item.empty:
        st.success(f"找到商品：{item['藥品名稱'].values[0]}")
        for col in display_columns:
            if col in item.columns:
                st.write(f"{col}：{item[col].values[0]}")
        if item['收貨狀態'].values[0] != '已收貨':
            if st.button("標記為已收貨"):
                df.loc[df['條碼'] == barcode, '收貨狀態'] = '已收貨'
                st.session_state['inventory_df'] = df
                st.success("商品已標記為已收貨")
                st.rerun()
        else:
            st.info("此商品已經收貨")
    else:
        st.error("未找到該商品，請檢查條碼是否正確")

# 保留其他原有的函數...

def main():
    st.title("藥品庫存管理系統")

    function = st.sidebar.radio("選擇功能", ("從 Google Drive 讀取", "檢貨", "收貨", "備份到 Google Drive"), key="function_selection")

    if function == "從 Google Drive 讀取":
        read_from_drive()
    elif function == "檢貨":
        check_inventory()
    elif function == "收貨":
        receive_inventory()
    elif function == "備份到 Google Drive":
        backup_to_drive()

    if st.button("測試 Google Drive 訪問"):
        test_drive_access()

if __name__ == "__main__":
    main()

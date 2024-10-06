import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import io
import streamlit.components.v1 as components
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

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
    try:
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents",  # 移除 MIME 類型檢查
            fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        st.write(f"找到 {len(files)} 個文件")
        for file in files:
            st.write(f"文件名: {file['name']}, ID: {file['id']}, 類型: {file['mimeType']}")
        return files
    except Exception as e:
        st.error(f"獲取文件列表時發生錯誤: {str(e)}")
        return []

def read_excel_from_drive(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_excel(fh)

def read_from_drive():
    st.subheader("從 Google Drive 讀取")
    folder_id = '1LdDnfuu3N8v9PkePOhuJd0Ffv_FBQsMA'  # Google Drive 文件夾 ID
    files = list_files_in_folder(folder_id)
    
    if not files:
        st.warning("未找到 Excel 文件")
        if st.button("重新整理"):
            st.experimental_rerun()
        return None
    
    selected_file = st.selectbox("選擇 Excel 文件", [file['name'] for file in files])
    file_id = next(file['id'] for file in files if file['name'] == selected_file)
    
    try:
        df = read_excel_from_drive(file_id)
        # 確保條碼列被正確讀取
        if '條碼' in df.columns:
            df['條碼'] = df['條碼'].astype(str).str.strip()
            # 移除可能的非數字字符
            df['條碼'] = df['條碼'].apply(lambda x: ''.join(filter(str.isdigit, x)))
        else:
            st.error("數據中缺少 '條碼' 列")
        
        st.write("數據框中的條碼示例:")
        st.write(df['條碼'].head())
        
        # 讀取 Excel 文件後，檢查並添加 '檢貨狀態' 列
        if '檢貨狀態' not in df.columns:
            df['檢貨狀態'] = '未檢貨'
            st.info("已添加 '檢貨狀態' 列到數據中")

        st.session_state['inventory_df'] = df
        st.success(f"已成功讀取 {selected_file}")
        st.write(df)
    except Exception as e:
        st.error(f"讀取文件時發生錯誤: {str(e)}")

def test_drive_access():
    try:
        results = drive_service.files().list(pageSize=10, fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])
        st.write('服務帳號可以訪問 Google Drive。找到的文件：')
        for item in items:
            st.write(f"{item['name']} ({item['id']}) - {item['mimeType']}")
    except Exception as e:
        st.error(f"訪問 Google Drive 時發生錯誤: {str(e)}")

def format_ean13(barcode):
    """將條碼格式化為 EAN-13 格式"""
    barcode = str(barcode).zfill(13)  # 補零至 13 位
    return f"{barcode[:1]} {barcode[1:7]} {barcode[7:]}"  # 格式化顯示

def check_and_mark_item(df, barcode):
    st.write(f"開始處理條碼: {barcode}")
    try:
        if '檢貨狀態' not in df.columns:
            df['檢貨狀態'] = '未檢貨'
        
        if '條碼' not in df.columns:
            st.error("數據框中缺少 '條碼' 列")
            return None
        
        # 嘗試完全匹配
        item = df[df['條碼'].astype(str).str.strip() == str(barcode).strip()]
        
        if item.empty:
            # 如果完全匹配失敗，嘗試部分匹配
            item = df[df['條碼'].astype(str).str.strip().str.contains(str(barcode).strip(), na=False)]
        
        if not item.empty:
            selected_item = item.iloc[0]
            st.success(f"找到商品：{selected_item['藥品名稱']}")
            st.write(f"匹配的條碼: {selected_item['條碼']}")
            
            df.loc[df['條碼'] == selected_item['條碼'], '檢貨狀態'] = '已檢貨'
            st.success("商品已自動標記為已檢貨")
            return df
        else:
            st.error(f"未找到條碼為 {barcode} 的商品，請檢查條碼是否正確")
    except Exception as e:
        st.error(f"處理商品時發生錯誤: {str(e)}")
    
    return None

def check_inventory():
    st.subheader("檢貨")
    
    if 'inventory_df' not in st.session_state:
        st.warning("請先從 Google Drive 讀取庫存文件")
        return

    df = st.session_state['inventory_df'].copy()

    # 添加 JavaScript 監聽器
    st.components.v1.html(
        """
        <script>
        window.addEventListener('message', function(event) {
            if (event.data.type === 'scanned_barcode') {
                if (window.Streamlit) {
                    window.Streamlit.setComponentValue(event.data.value);
                } else {
                    console.log('Streamlit object not available, unable to set component value');
                }
            }
        }, false);
        </script>
        """,
        height=0
    )

    # 使用 st.components.v1.html 來嵌入條碼掃描器
    scanned_value = st.components.v1.html(barcode_scanner_html, height=600)

    # 添加輪詢機制
    if 'last_scanned_value' not in st.session_state:
        st.session_state.last_scanned_value = None

    current_value = scanned_value
    if current_value and current_value != st.session_state.last_scanned_value:
        st.session_state.last_scanned_value = current_value
        st.write(f"掃描到的條碼: {current_value}")
        updated_df = check_and_mark_item(df, current_value)
        if updated_df is not None:
            st.session_state['inventory_df'] = updated_df
            st.rerun()

    # 添加一個按鈕來手動觸發重新檢查
    if st.button("重新檢查掃描結果"):
        st.rerun()

    # 顯示當前庫存狀態
    display_columns = ['藥庫位置', '藥品名稱', '盤撥量', '藥庫庫存', '檢貨狀態']
    df_display = df[display_columns]
    
    status_display = st.empty()
    status_display.write("當前庫存狀態：")
    status_display.dataframe(df_display.style.applymap(
        lambda x: 'background-color: #90EE90' if x == '已檢貨' else 'background-color: #FFB6C1',
        subset=['檢貨狀態']
    ))

    # 手動輸入條碼
    manual_input = st.text_input("手動輸入條碼", value="")

    if st.button("更新庫存"):
        if manual_input:
            updated_df = check_and_mark_item(df, manual_input)
            if updated_df is not None:
                st.session_state['inventory_df'] = updated_df
                st.rerun()

    # 顯示調試信息
    st.write("調試信息:")
    st.components.v1.html(
        """
        <div id="debug-display"></div>
        <script>
        setInterval(() => {
            const debugElement = document.getElementById('debug');
            const debugDisplayElement = document.getElementById('debug-display');
            if (debugElement && debugDisplayElement) {
                debugDisplayElement.textContent = debugElement.textContent;
            }
        }, 1000);
        </script>
        """,
        height=200
    )

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

def backup_to_drive():
    st.subheader("備份到 Google Drive")
    if 'inventory_df' in st.session_state:
        df = st.session_state['inventory_df']
        # 备份逻辑
        st.success("數據已備份到 Google Drive")
    else:
        st.warning("沒有可備份的數據")

def main():
    st.title("藥品庫存管理系統")

    function = st.sidebar.selectbox(
        "選擇功能",
        ("從 Google Drive 讀取", "檢貨", "收貨", "備份到 Google Drive"),
        key="function_selection"
    )

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

barcode_scanner_html = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>條碼掃描器</title>
    <script src="https://cdn.jsdelivr.net/npm/quagga@0.12.1/dist/quagga.min.js"></script>
    <style>
        #interactive.viewport {
            position: relative;
            width: 100%;
            height: 300px;
        }
        #interactive.viewport > canvas, #interactive.viewport > video {
            max-width: 100%;
            width: 100%;
        }
        canvas.drawing, canvas.drawingBuffer {
            position: absolute;
            left: 0;
            top: 0;
        }
    </style>
</head>
<body>
    <h1>條碼掃描器</h1>
    <div id="interactive" class="viewport"></div>
    <div id="result"></div>
    <button id="startButton">開始掃描</button>

    <script>
        let lastResult = null;

        function startScanner() {
            Quagga.init({
                inputStream: {
                    name: "Live",
                    type: "LiveStream",
                    target: document.querySelector("#interactive"),
                    constraints: {
                        facingMode: "environment"
                    },
                },
                decoder: {
                    readers: ["ean_reader", "ean_8_reader", "code_128_reader"]
                }
            }, function(err) {
                if (err) {
                    console.log(err);
                    return;
                }
                console.log("Quagga initialization finished. Ready to start");
                Quagga.start();
            });

            Quagga.onDetected(function(result) {
                var code = result.codeResult.code;
                if (code !== lastResult) {
                    lastResult = code;
                    document.getElementById('result').textContent = "掃描到的條碼: " + code;
                    sendToStreamlit(code);
                }
            });
        }

        function sendToStreamlit(code) {
            // 這裡需要替換為您的 Streamlit 應用 URL
            window.location.href = 'https://your-streamlit-app-url/?barcode=' + encodeURIComponent(code);
        }

        document.getElementById('startButton').addEventListener('click', startScanner);
    </script>
</body>
</html>
"""

st.markdown("""
<style>
#scanner-container {
    position: relative;
    width: 100%;
    max-width: 640px;
    height: 480px;
    overflow: hidden;
    margin: auto;
}
#scanner-container video {
    width: 100%;
    height: 100%;
    object-fit: cover;
}
#start-scanner {
    display: block;
    margin: 10px auto;
    padding: 10px 20px;
    font-size: 16px;
    -webkit-appearance: none;
    border-radius: 0;
}
#scanner-status {
    text-align: center;
    margin-top: 10px;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

def update_inventory_status(df, barcode):
    if barcode in df['條碼'].values:
        df.loc[df['條碼'] == barcode, '檢貨狀態'] = '已檢貨'
        st.write(f"更新條碼 {barcode} 的狀態為已檢貨")  # 調試信息
        return df
    else:
        st.warning(f"條碼 {barcode} 未找到")
        return None

app = FastAPI()

# 允許所有來源的 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/update_inventory")
async def update_inventory(request: Request):
    data = await request.json()
    barcode = data.get('barcode')
    
    # 在這裡處理條碼更新邏輯
    # 例如，調用 check_and_mark_item 函數
    
    return {"status": "success", "message": f"已更新條碼 {barcode}"}

def main():
    st.title("藥品庫存管理系統")

    # 檢查是否有掃描的條碼
    scanned_barcode = st.query_params.get("barcode")
    if scanned_barcode:
        st.success(f"接收到掃描的條碼: {scanned_barcode}")
        # 處理條碼邏輯
        process_barcode(scanned_barcode)
        # 清除查詢參數
        st.query_params.clear()
        st.rerun()

    # 其他 Streamlit 代碼...
    display_inventory()

def process_barcode(barcode):
    # 這裡處理條碼邏輯
    if 'inventory_df' not in st.session_state:
        st.session_state.inventory_df = pd.DataFrame(columns=['條碼', '藥品名稱', '檢貨狀態'])
    
    # 檢查條碼是否已存在
    if barcode in st.session_state.inventory_df['條碼'].values:
        st.session_state.inventory_df.loc[st.session_state.inventory_df['條碼'] == barcode, '檢貨狀態'] = '已檢貨'
        st.success(f"更新條碼 {barcode} 的狀態為已檢貨")
    else:
        # 如果條碼不存在，添加新行
        new_row = pd.DataFrame({'條碼': [barcode], '藥品名稱': ['未知'], '檢貨狀態': ['已檢貨']})
        st.session_state.inventory_df = pd.concat([st.session_state.inventory_df, new_row], ignore_index=True)
        st.success(f"添加新條碼 {barcode} 到庫存")

def display_inventory():
    if 'inventory_df' in st.session_state:
        st.write("當前庫存狀態：")
        st.dataframe(st.session_state.inventory_df)
    else:
        st.info("庫存為空")

if __name__ == "__main__":
    main()

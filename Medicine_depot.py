import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import io
import streamlit.components.v1 as components

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
        # 讀取 Excel 文件後，檢查並添加 '檢貨狀態' 列
        if '檢貨狀態' not in df.columns:
            df['檢貨狀態'] = '未檢貨'
            st.info("已添加 '檢貨狀態' 列到數據中")

        # 確保條碼列被正確讀取
        if '條碼' in df.columns:
            df['條碼'] = df['條碼'].astype(str).str.strip()
        else:
            st.error("數據中缺少 '條碼' 列")

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

def check_inventory():
    st.subheader("檢貨")
    
    if 'inventory_df' not in st.session_state:
        st.warning("請先從 Google Drive 讀取庫存文件")
        if st.button("前往讀取數據"):
            st.session_state.function_selection = "從 Google Drive 讀取"
            st.rerun()
        return

    df = st.session_state['inventory_df']
    
    # 顯示所有可用的列
    st.write("可用的列：", df.columns.tolist())
    
    # 定義我們想要顯示的列
    desired_columns = ['藥庫位置', '藥品名稱', '盤撥量', '藥庫庫存', '檢貨狀態']
    
    # 檢查哪些列實際存在於數據框中
    available_columns = [col for col in desired_columns if col in df.columns]
    
    if not available_columns:
        st.error("數據框中沒有找到任何所需的列。請檢查數據格式。")
        return
    
    # 只選擇可用的列
    df_display = df[available_columns]

    # 顯示當前庫存狀態
    st.write("當前庫存狀態：")
    if '檢貨狀態' in available_columns:
        st.dataframe(df_display.style.applymap(
            lambda x: 'background-color: #90EE90' if x == '已檢貨' else 'background-color: #FFB6C1',
            subset=['檢貨狀態']
        ))
    else:
        st.dataframe(df_display)

    # 添加條碼掃描功能
    barcode_scanner_html = """
    <div id="scanner-container"></div>
    <input type="text" id="barcode-input" style="display:none;">
    <button id="start-scanner">開始/停止掃描</button>
    <div id="scanner-status"></div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/quagga/0.12.1/quagga.min.js"></script>
    <script>
        var scannerIsRunning = false;

        function startScanner() {
            Quagga.init({
                inputStream: {
                    name: "Live",
                    type: "LiveStream",
                    target: document.querySelector('#scanner-container'),
                    constraints: {
                        width: 640,
                        height: 480,
                        facingMode: "environment"
                    },
                },
                decoder: {
                    readers: [
                        "ean_reader",
                        "ean_8_reader",
                        "code_128_reader",
                        "code_39_reader",
                        "code_39_vin_reader",
                        "codabar_reader",
                        "upc_reader",
                        "upc_e_reader",
                        "i2of5_reader"
                    ],
                    debug: {
                        showCanvas: true,
                        showPatches: true,
                        showFoundPatches: true,
                        showSkeleton: true,
                        showLabels: true,
                        showPatchLabels: true,
                        showRemainingPatchLabels: true,
                        boxFromPatches: {
                            showTransformed: true,
                            showTransformedBox: true,
                            showBB: true
                        }
                    }
                },
                locate: true,
                frequency: 10
            }, function(err) {
                if (err) {
                    console.log(err);
                    document.querySelector('#scanner-status').textContent = "無法啟動掃描器：" + err;
                    return;
                }
                Quagga.start();
                scannerIsRunning = true;
                document.querySelector('#scanner-status').textContent = "掃描器已啟動";
            });

            Quagga.onDetected(function(result) {
                var code = result.codeResult.code;
                document.querySelector('#barcode-input').value = code;
                document.querySelector('#barcode-input').dispatchEvent(new Event('change'));
                document.querySelector('#scanner-status').textContent = "已掃描到條碼：" + code;
                // 不要自動停止掃描器
            });
        }

        document.querySelector('#start-scanner').addEventListener('click', function() {
            if (scannerIsRunning) {
                Quagga.stop();
                scannerIsRunning = false;
                this.textContent = "開始掃描";
                document.querySelector('#scanner-status').textContent = "掃描器已停止";
            } else {
                startScanner();
                this.textContent = "停止掃描";
            }
        });
    </script>
    """
    
    components.html(barcode_scanner_html, height=600)

    # 使用 form 來確保條碼輸入後可以立即處理
    with st.form(key='barcode_form'):
        barcode = st.text_input("輸入商品條碼或掃描條碼", key="barcode_input")
        submit_button = st.form_submit_button("檢查商品")

    if submit_button or barcode:
        check_item(df, barcode, available_columns)

    # 顯示檢貨進度
    if '檢貨狀態' in df.columns:
        total_items = len(df)
        checked_items = len(df[df['檢貨狀態'] == '已檢貨'])
        progress = checked_items / total_items
        st.progress(progress)
        st.write(f"檢貨進度：{checked_items}/{total_items} ({progress:.2%})")
    else:
        st.warning("無法顯示檢貨進度，因為數據框中缺少 '檢貨狀態' 列")

def check_item(df, barcode, display_columns):
    st.write(f"正在查找條碼：{barcode}")
    st.write("數據框列名：", df.columns.tolist())
    
    if '條碼' not in df.columns:
        st.error("數據框中缺少 '條碼' 列")
        return
    
    # 顯示所有條碼，以便進行調試
    st.write("數據框中的所有條碼：", df['條碼'].tolist())
    
    # 嘗試不同的匹配方法
    item = df[df['條碼'].astype(str) == str(barcode)]
    if item.empty:
        item = df[df['條碼'].astype(str).str.contains(str(barcode))]
    
    if not item.empty:
        st.success(f"找到商品：{item['藥品名稱'].values[0] if '藥品名稱' in item.columns else '未知商品'}")
        for col in display_columns:
            if col in item.columns:
                st.write(f"{col}：{item[col].values[0]}")
        if '檢貨狀態' in item.columns and item['檢貨狀態'].values[0] != '已檢貨':
            if st.button("標記為已檢貨"):
                df.loc[df['條碼'].astype(str) == str(barcode), '檢貨狀態'] = '已檢貨'
                st.session_state['inventory_df'] = df
                st.success("商品已標記為已檢貨")
                st.rerun()
        elif '檢貨狀態' in item.columns:
            st.info("此商品已經檢貨")
        else:
            st.warning("無法更新檢貨狀態，因為數據框中缺少 '檢貨狀態' 列")
    else:
        st.error(f"未找到條碼為 {barcode} 的商品，請檢查條碼是否正確")
        # 顯示與輸入條碼最相似的幾個條碼，以幫助診斷問題
        similar_barcodes = df['條碼'].astype(str).sort_values(key=lambda x: x.str.find(str(barcode)), ascending=True).head()
        st.write("最相似的條碼：", similar_barcodes.tolist())

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

st.markdown("""
<style>
#scanner-container {
    position: relative;
    width: 320px;
    height: 240px;
    overflow: hidden;
}
#scanner-container video {
    width: 320px;
    height: 240px;
    object-fit: cover;
}
</style>
""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()

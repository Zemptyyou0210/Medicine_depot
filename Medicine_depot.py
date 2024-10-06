import streamlit as st
import pandas as pd

def main():
    st.title("貨品庫存管理系統")
    
    menu = ["查看庫存", "添加商品", "更新庫存", "刪除商品", "條碼掃描"]
    choice = st.sidebar.selectbox("選擇操作", menu)
    
    if choice == "查看庫存":
        view_inventory()
    elif choice == "添加商品":
        add_product()
    elif choice == "更新庫存":
        update_inventory()
    elif choice == "刪除商品":
        delete_product()
    elif choice == "條碼掃描":
        barcode = barcode_scanner()
        if barcode:
            st.write(f"掃描到的條碼: {barcode}")
            # 處理掃描到的條碼

if __name__ == "__main__":
    main()

def view_inventory():
    st.subheader("當前庫存")
    # 從 Firebase 獲取數據
    docs = db.collection('inventory').stream()
    data = [{**doc.to_dict(), 'id': doc.id} for doc in docs]
    df = pd.DataFrame(data)
    st.dataframe(df)

def add_product():
    st.subheader("添加新商品")
    name = st.text_input("商品名稱")
    quantity = st.number_input("數量", min_value=0)
    price = st.number_input("價格", min_value=0.0)
    if st.button("添加"):
        # 添加到 Firebase
        db.collection('inventory').add({
            'name': name,
            'quantity': quantity,
            'price': price
        })
        st.success("商品已添加")

def update_inventory():
    st.subheader("更新庫存")
    docs = db.collection('inventory').stream()
    products = {doc.to_dict()['name']: doc.id for doc in docs}
    product = st.selectbox("選擇商品", list(products.keys()))
    new_quantity = st.number_input("新數量", min_value=0)
    if st.button("更新"):
        # 更新 Firebase
        db.collection('inventory').document(products[product]).update({
            'quantity': new_quantity
        })
        st.success("庫存已更新")

def delete_product():
    st.subheader("刪除商品")
    docs = db.collection('inventory').stream()
    products = {doc.to_dict()['name']: doc.id for doc in docs}
    product = st.selectbox("選擇要刪除的商品", list(products.keys()))
    if st.button("刪除"):
        # 從 Firebase 刪除
        db.collection('inventory').document(products[product]).delete()
        st.success("商品已刪除")

def barcode_scanner():
    st.subheader("條碼掃描")
    scanner_html = """
    <div id="scanner-container"></div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/quagga/0.12.1/quagga.min.js"></script>
    <script>
        Quagga.init({
            inputStream : {
                name : "Live",
                type : "LiveStream",
                target: document.querySelector('#scanner-container')
            },
            decoder : {
                readers : ["ean_reader", "ean_8_reader", "code_128_reader"]
            }
        }, function(err) {
            if (err) {
                console.log(err);
                return
            }
            console.log("Initialization finished. Ready to start");
            Quagga.start();
        });
        Quagga.onDetected(function(result) {
            Quagga.stop();
            Streamlit.setComponentValue(result.codeResult.code);
        });
    </script>
    """
    scanned_code = st.components.v1.html(scanner_html, height=300)
    return scanned_code

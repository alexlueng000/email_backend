from sqlalchemy import create_engine, text

from sqlalchemy.exc import SQLAlchemyError

# ==== 修改为你的MySQL连接信息 ====
host = '127.0.0.1'
port = 3306
user = 'testuser'
password = 'test123'
database = 'bidding_emails'
table_name = 'company_info'


engine = create_engine(f'mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4')

adding_c_company = """
INSERT INTO `company_info` (`company_type`, `company_name`, `short_name`, `contact_person`, `last_name`, `last_name_traditional`, `phone`, `email`, `address`, `english_address`) VALUES
('C', '深圳市弗劳恩科技服务有限公司', 'FW', '向南 ', '向', '向', '13902431183', 'szflekjfw@yeah.net', '深圳市罗湖区南湖街道新南社区深南东路2001号鸿昌广场1301', 'Room1301, Hong Chang Plaza ,No.2001 Shennan East Road, Xinnan Community, Nanhu Street ,Luohu  District, Shenzhen, China'),
('C', '深圳市赛纳精密仪器有限公司', 'SN', '万丽华 ', '万', '萬', '+86 13316908196', 'KQ18SETTLma@163.com', '深圳市福田区深南中路2070号电子科技大厦C座10D 2-9', 'Apartment 1907B1D, International Culture Building, No. 3039, Shennan Middle Road, Funan Community, Futian Subdistrict, Futian District, Shenzhen, China.'),
('C', '深圳市启慧仪器有限公司', 'QH', '李晓娜 ', '李', '李', '13316883640', 'y04nmyhsi5ngznw@163.com', '深圳市福田区福田街道福山社区滨河大道5022号联合广场A座4410B60', NULL);

"""

# 执行 SQL 并提交
try:
    with engine.connect() as conn:
        with conn.begin():  # ✅ 开启事务并自动提交
            conn.execute(text(adding_c_company))
    print("插入成功！")
except SQLAlchemyError as e:
    print("执行失败：", e)

# with pymysql.connect(host=host, user=user, password=password) as conn:
#     with conn.cursor() as cursor:
#         cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database} DEFAULT CHARACTER SET utf8mb4;")
#     conn.commit()

# ==== 创建表结构（不含邮箱密码） ====
create_table_sql = f"""
CREATE TABLE IF NOT EXISTS {table_name} (
    id INT AUTO_INCREMENT PRIMARY KEY,
    company_type VARCHAR(100),
    company_name VARCHAR(255),
    short_name VARCHAR(100),
    contact_person VARCHAR(100),
    last_name VARCHAR(100),
    last_name_traditional VARCHAR(100),
    phone VARCHAR(100),
    email VARCHAR(255),
    address TEXT,
    english_address TEXT
) CHARACTER SET utf8mb4;
"""

# 创建project_info表
create_project_info_table = f"""
CREATE TABLE IF NOT EXISTS project_info (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(255),
    contract_number VARCHAR(100),
    tender_number VARCHAR(100),
    project_type VARCHAR(100),
    p_serial_number VARCHAR(100),
    l_serial_number VARCHAR(100),
    f_serial_number VARCHAR(100),
    purchaser VARCHAR(255),
    company_b_name VARCHAR(255),
    company_c_name VARCHAR(255),
    company_d_name VARCHAR(255),
    a1 TINYINT(1),
    a2 TINYINT(1),
    b3 TINYINT(1),
    b4 TINYINT(1),
    b5 TINYINT(1),
    b6 TINYINT(1),
    c7 TINYINT(1),
    c8 TINYINT(1),
    c9 TINYINT(1),
    c10 TINYINT(1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4;
"""

# 创建email_subject表
create_email_subject = f"""
CREATE TABLE email_subject (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stage VARCHAR(50),              -- 阶段，如 first, reply 等
    company_name VARCHAR(255),      -- 公司全名
    short_name VARCHAR(100),        -- 公司简称
    subject TEXT,                   -- 可用于 Python 格式化的文本
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4;
"""

# emails_records表中加一列
# alter_email_records = f"""
# ALTER TABLE emails_records ADD COLUMN task_id VARCHAR(100);
# """

alter_email_records = """
ALTER TABLE emails_records
ADD COLUMN project_id INT,
ADD COLUMN stage VARCHAR(50);
"""
# alter_email_records = f"""
# ALTER TABLE emails_records ADD COLUMN task_id VARCHAR(100), project_id INT, stage VARCHAR(50);
# """

insert_email_subject = """
INSERT INTO email_subject (stage, company_name, short_name, subject)
VALUES
    ('B3', '深圳市深业晋展物料供应有限公司', 'JZ', '{project_name} {serial_number}'),
    ('B3', '深圳市弗劳恩科技服务有限公司', 'FW', '{project_name} 编号：{serial_number}'),
    ('B3', '深圳市立达方圆物料供应有限公司', 'LD', '{project_name} {serial_number}'),
    ('B3', '深圳市德贯科技有限公司', 'DG', '{project_name} {serial_number}'),
    ('B3', '深圳市赛纳精密仪器有限公司', 'SN', '{project_name} 外贸服务 {serial_number}'),
    ('B3', '深圳市拓踏科技有限公司', 'TT', '{project_name} 外贸服务 {serial_number}'),
    ('B3', '深圳市智翰仪器有限公司', 'ZH', '{project_name} _业务委托_ {serial_number}'),
    ('B3', '深圳市乔孚科技有限公司', 'QF', '{project_name} {serial_number}'),
    ('B3', '深圳市泽意仪器有限公司', 'ZY', '【外贸服务委托】{project_name} {serial_number}'),
    ('B3', '深圳市久业科技仪器有限公司', 'JY', '{project_name} {serial_number}'),
    ('B3', '深圳市雅怡科技仪器有限公司', 'YY', '{project_name}/{serial_number}'),
    ('B3', '深圳市启慧仪器有限公司', 'QH', '{project_name} {serial_number}'),
    ('B3', '深圳市佰志诚科技发展有限公司', 'BZC', '{project_name} 外贸服务 {serial_number}'),
    ('B3', '深圳市礼恒科技有限公司', 'LH', '{project_name} {serial_number}'),
    ('B3', '深圳市海辰星科技有限公司', 'HCX', '{project_name} 外贸委托 {serial_number}'),
    ('B4', '深圳市深业晋展物料供应有限公司', 'JZ', '{contract_number} {project_name} {serial_number}'),
    ('B4', '深圳市立达方圆物料供应有限公司', 'LD', '{contract_number} {project_name} {serial_number}'),
    ('B4', '深圳市德贯科技有限公司', 'DG', '{project_name} （合同编号：{contract_number}）{serial_number}'),
    ('B5', '深圳市深业晋展物料供应有限公司', 'JZ', '{contract_number} {project_name} {serial_number}'),
    ('B5', '深圳市弗劳恩科技服务有限公司', 'FW', '{project_name} 编号：{serial_number}'),
    ('B5', '深圳市立达方圆物料供应有限公司', 'LD', '{project_name} 中标金额：{contract_amount} {serial_number}'),
    ('B5', '深圳市赛纳精密仪器有限公司', 'SN', '【中标通知】{project_name} {serial_number}'),
    ('B5', '深圳市拓踏科技有限公司', 'TT', '{project_name} _({bidding_confirm_time}) 中标_中标金额：{contract_amount} _ {serial_number}'),
    ('B5', '深圳市智翰仪器有限公司', 'ZH', '好消息！{project_name} 已中标 {serial_number}'),
    ('B5', '深圳市德贯科技有限公司', 'DG', '{project_name} {serial_number}'),
    ('B5', '深圳市乔孚科技有限公司', 'QF', '{project_name} {serial_number}'),
    ('B5', '深圳市泽意仪器有限公司', 'ZY', '【招标结果】招标编号为{tender_number} {project_name}已中标{serial_number}'),
    ('B5', '深圳市久业科技仪器有限公司', 'JY', '{project_name}（项目编号：{tender_number}）{serial_number}'),
    ('B5', '深圳市雅怡科技仪器有限公司', 'YY', '{project_name}/招标编号：{tender_number}/{serial_number}'),
    ('B5', '深圳市启慧仪器有限公司', 'QH', '{project_name} {serial_number}'),
    ('B5', '深圳市佰志诚科技发展有限公司', 'BZC', '{project_name} {serial_number}'),
    ('B5', '深圳市礼恒科技有限公司', 'LH', '{tender_number} {project_name} {serial_number}'),
    ('B5', '深圳市海辰星科技有限公司', 'HCX', '{project_name} 中标通知 {serial_number}'),
    ('B6', 'leaderfirm Technology Company Limited', '领先/leaderfirm', '{project_name}- 中標履約| {company_b_name} | {serial_number}'),
    ('B6', 'FRAUN SCIENCE AND TECHNOLOGY SERVICE COMPANY LIMITED', '香港FRAUN', '【專案執行】{project_name} {serial_number}'),
    ('B6', 'PRECISE INSTRUMENT COMPANY LIMITED', 'PRECISE', '{project_name}採購項目 {serial_number}'),
    ('C7', '深圳市深业晋展物料供应有限公司', 'JZ', '{contract_number} {project_name}结算发送 {serial_number}'),
    ('C7', '深圳市弗劳恩科技服务有限公司', 'FW', '{project_name} 编号：{serial_number}'),
    ('C7', '深圳市立达方圆物料供应有限公司', 'LD', '{contract_number} {project_name}结算  {serial_number}'),
    ('C7', '深圳市赛纳精密仪器有限公司', 'SN', '【结算单】{contract_number} {project_name} {serial_number}'),
    ('C7', '深圳市拓踏科技有限公司', 'TT', '{project_name} _({bidding_confirm_time}) 中标_中标金额：{contract_amount} _ {serial_number}'),
    ('C7', '深圳市智翰仪器有限公司', 'ZH', '好消息！{project_name} 已中标 {serial_number}'),
    ('C7', '深圳市德贯科技有限公司', 'DG', '{project_name}（合同编号：{contract_number}）结算单  {serial_number}'),
    ('C7', '深圳市乔孚科技有限公司', 'QF', '{project_name} {serial_number}'),
    ('C7', '深圳市泽意仪器有限公司', 'ZY', '【招标结果】招标编号为{tender_number} {project_name}已中标{serial_number}'),
    ('C7', '深圳市久业科技仪器有限公司', 'JY', '{project_name}（项目编号：{tender_number}）{serial_number}'),
    ('C7', '深圳市雅怡科技仪器有限公司', 'YY', '{project_name}/招标编号：{tender_number}/{serial_number}'),
    ('C7', '深圳市启慧仪器有限公司', 'QH', '{contract_number}{project_name} {serial_number}'),
    ('C7', '深圳市佰志诚科技发展有限公司', 'BZC', '{project_name} {serial_number}'),
    ('C7', '深圳市礼恒科技有限公司', 'LH', '{tender_number} {project_name} {serial_number}'),
    ('C7', '深圳市海辰星科技有限公司', 'HCX', '{project_name} 中标通知 {serial_number}'),
    ('C8', '深圳市深业晋展物料供应有限公司', 'JZ', '{contract_number} {project_name} 结算发送 {serial_number}'),
    ('C8', '深圳市弗劳恩科技服务有限公司', 'FW', '{project_name} 编号：{serial_number}'),
    ('C8', '深圳市立达方圆物料供应有限公司', 'LD', '{project_name} 中标金额：{contract_amount} {serial_number}'),
    ('C8', '深圳市德贯科技有限公司', 'DG', '{project_name} {serial_number}'),
    ('C8', '深圳市赛纳精密仪器有限公司', 'SN', '【结算单】{contract_number} {project_name} {serial_number}'),
    ('C8', '深圳市拓踏科技有限公司', 'TT', '{project_name} _({bidding_confirm_time}) 中标_中标金额：{contract_amount} _ {serial_number}'),
    ('C8', '深圳市智翰仪器有限公司', 'ZH', '{project_name} _业务委托_ {serial_number}'),
    ('C8', '深圳市乔孚科技有限公司', 'QF', '合同号：{contract_number} {project_name} 结算审核 {serial_number}'),
    ('C8', '深圳市泽意仪器有限公司', 'ZY', '【结算清单】招标编号为{tender_number} {project_name}已结算{serial_number}'),
    ('C8', '深圳市久业科技仪器有限公司', 'JY', '{project_name}（项目编号：{tender_number}）{serial_number}'),
    ('C8', '深圳市雅怡科技仪器有限公司', 'YY', '{project_name}/招标编号：{tender_number}/{serial_number}'),
    ('C8', '深圳市启慧仪器有限公司', 'QH', '{contract_number} {project_name} {serial_number}'),
    ('C8', '深圳市佰志诚科技发展有限公司', 'BZC', '{contract_number} {project_name} {serial_number}'),
    ('C8', '深圳市礼恒科技有限公司', 'LH', '{tender_number} {project_name} {serial_number}'),
    ('C8', '深圳市海辰星科技有限公司', 'HCX', '{project_name}（合同号：{contract_number}）结算文件 {serial_number}'),
    ('C9', 'leaderfirm Technology Company Limited', '领先/leaderfirm', '{project_name}- 結算確認| {company_b_name} | {serial_number}'),
    ('C9', 'FRAUN SCIENCE AND TECHNOLOGY SERVICE COMPANY LIMITED', '香港FRAUN', '【結算】{project_name} {serial_number}'),
    ('C9', 'PRECISE INSTRUMENT COMPANY LIMITED', 'PRECISE', '{project_name}結算確認 {serial_number}'),
    ('C10', '深圳市深业晋展物料供应有限公司', 'JZ', '{contract_number} {project_name} 结算发送 {serial_number}'),
    ('C10', '深圳市弗劳恩科技服务有限公司', 'FW', '{project_name} 编号：{serial_number}'), 
    ('C10', '深圳市立达方圆物料供应有限公司', 'LD', '{project_name} 中标金额：{contract_amount} {serial_number}'),
    ('C10', '深圳市德贯科技有限公司', 'DG', '{project_name} {serial_number}'),
    ('C10', '深圳市赛纳精密仪器有限公司', 'SN', '【结算单】{contract_number} {project_name} {serial_number}'),
    ('C10', '深圳市拓踏科技有限公司', 'TT', '{project_name} _({bidding_confirm_time}) 中标_中标金额：{contract_amount} _ {serial_number}'),
    ('C10', '深圳市智翰仪器有限公司', 'ZH', '{project_name} _业务委托_ {serial_number}'),
    ('C10', '深圳市乔孚科技有限公司', 'QF', '合同号：{contract_number} {project_name} 结算审核 {serial_number}'),
    ('C10', '深圳市泽意仪器有限公司', 'ZY', '【结算清单】招标编号为{tender_number} {project_name}已结算{serial_number}'),
    ('C10', '深圳市久业科技仪器有限公司', 'JY', '{project_name}（项目编号：{tender_number}）{serial_number}'),
    ('C10', '深圳市雅怡科技仪器有限公司', 'YY', '{project_name}/招标编号：{tender_number}/{serial_number}'),
    ('C10', '深圳市启慧仪器有限公司', 'QH', '{contract_number} {project_name} {serial_number}'),
    ('C10', '深圳市佰志诚科技发展有限公司', 'BZC', '{contract_number} {project_name} {serial_number}'),
    ('C10', '深圳市礼恒科技有限公司', 'LH', '{tender_number} {project_name} {serial_number}'),
    ('C10', '深圳市海辰星科技有限公司', 'HCX', '{project_name}（合同号：{contract_number}）结算文件 {serial_number}');
"""


# ==== 写入数据库 ====
# df.to_sql(table_name, con=engine, if_exists='append', index=False)

# print("✅ 已成功导入（不含邮箱密码）！")
# print("创建project_info表成功！")


# def test_db_connection(user, password, host, port, database):
#     try:
#         engine = create_engine(
#             f'mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4'
#         )
#         with engine.connect() as conn:
#             result = conn.execute(text("SELECT 1"))
#             print("✅ 数据库连接成功，测试查询结果:", result.scalar())
#         return True
#     except SQLAlchemyError as e:
#         print("❌ 数据库连接失败:", str(e))
#         return False


# if __name__ == "__main__":
#     test_db_connection(user, password, host, port, database)
    
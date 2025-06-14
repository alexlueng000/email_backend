import os

# 定义 short_name 列表
short_names = [
    'FW', 'LD', 'DG', 'SN', 'ZH', 'QF', 'ZY',
    'JY', 'YY', 'QH', 'BZC', 'LH', 'HCX'
]

c_company_short_names = [
    'JZ', 'FW', 'LD', 'SN', 'DG', 'QH'
]

# 要创建文件的目录（当前目录）
output_dir = "app/email_templates"

# 执行创建文件
for short_name in c_company_short_names:
    filename = f"B5_{short_name}_SPEC.html"
    filepath = os.path.join(output_dir, filename)

    # 创建空文件
    with open(filepath, "w", encoding="utf-8") as f:
        pass  # 空内容

    print(f"已创建：{filename}")
import mysql.connector
import os
import glob
import re

# 运行目录 sfbackend

# 数据库配置，请根据实际情况修改
db_config = {
    'host': '192.168.1.225',
    'port': 3306,
    'user': 'root',
    'password': 'kdi@#Qp98',
    'database': 'dxds_iop',
    'charset': 'utf8mb4'
}


def detect_file_encoding(file_path):
    """检测Python文件的编码"""
    # 常见编码列表，按优先级排序
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1', 'ascii']

    # 先读取前两行检测编码声明
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(4096)
    except Exception:
        return None

    # 空文件默认UTF-8
    if not raw_data:
        return 'utf-8'

    # 检测BOM标记
    if raw_data.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    if raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):
        return 'utf-16'

    # 尝试从文件头部提取编码声明
    try:
        # 用ascii解码头部来查找编码声明
        header = raw_data[:1024].decode('ascii', errors='ignore')
        # 匹配 # -*- coding: xxx -*- 或 # coding: xxx 或 # coding= xxx
        pattern = r'coding[=:]\s*([-\w.]+)'
        match = re.search(pattern, header)
        if match:
            declared = match.group(1).lower()
            # 标准化编码名称
            if declared in ('utf8', 'utf-8'):
                return 'utf-8'
            elif declared in ('gbk',):
                return 'gbk'
            elif declared in ('gb2312',):
                return 'gb2312'
            elif declared in ('gb18030',):
                return 'gb18030'
            elif declared in ('latin1', 'latin-1', 'iso-8859-1'):
                return 'latin-1'
            elif declared in ('ascii',):
                return 'ascii'
    except Exception:
        pass

    # 依次尝试常见编码
    for enc in encodings:
        try:
            raw_data.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue

    return 'latin-1'  # latin-1 可以解码任何字节序列


def read_file_content(file_path):
    """安全读取文件内容，自动处理编码"""
    # 先检测编码
    encoding = detect_file_encoding(file_path)
    if encoding is None:
        return None, "无法读取文件"

    # 尝试用检测到的编码读取
    try:
        with open(file_path, 'r', encoding=encoding, errors='strict') as f:
            return f.read(), None
    except UnicodeDecodeError:
        # 如果strict模式失败，用replace模式
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                return f.read(), None
        except Exception as e:
            return None, str(e)
    except Exception as e:
        return None, str(e)


def update_scripts_content():
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        scripts_dir = 'pyfiles'
        py_files = glob.glob(os.path.join(scripts_dir, '**/*.py'), recursive=True)

        if not py_files:
            print("scripts目录下没有找到Python文件")
            return

        updated_count = 0
        skipped_count = 0

        for file_path in py_files:
            filename = os.path.basename(file_path)

            content, error = read_file_content(file_path)
            if error:
                print(f"[跳过] {filename}: {error}")
                skipped_count += 1
                continue

            query = "SELECT unique_key FROM t_system_enhance_dir WHERE type = 'file' AND name = %s"
            cursor.execute(query, (filename,))
            result = cursor.fetchone()

            if result:
                unique_key = result[0]
                update_query = "UPDATE t_system_enhance_file SET content = %s WHERE unique_key = %s"
                cursor.execute(update_query, (content, unique_key))
                print(f"[更新] {filename} (key: {unique_key})")
                updated_count += 1
            else:
                print(f"[未匹配] {filename}")

        conn.commit()
        print(f"\n完成: 更新 {updated_count} 个, 跳过 {skipped_count} 个")

    except mysql.connector.Error as e:
        print(f"数据库错误: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"发生错误: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    update_scripts_content()

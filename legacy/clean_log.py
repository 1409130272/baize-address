import glob
import os
import time
import shutil

dir_path = os.path.dirname(os.path.abspath(__file__))

if not os.path.exists(f'{dir_path}/log'):
    os.mkdir(f'{dir_path}/log')
def clean():
    file_list = glob.glob(os.path.join(f'{dir_path}/log/', '*'))
    for file_dir in file_list:
        file_create_timestamp = os.path.getmtime(file_dir)
        now_timestamp = time.time()
        exceed_seconds = now_timestamp - file_create_timestamp
        # 判断文件生成时间，文件生成超过24小时再删除
        if exceed_seconds >= 24 * 60 * 60 * 7:
            try:
                if os.path.isfile(file_dir):
                    os.remove(file_dir)
                elif os.path.isdir(file_dir):
                    shutil.rmtree(file_dir)
                print(f"删除{file_dir}成功")
            except FileNotFoundError:
                print(f"要删除的{file_dir}文件不存在")
        else:
            print(f"要删除的{file_dir}未超时")


if __name__ == "__main__":
    clean()
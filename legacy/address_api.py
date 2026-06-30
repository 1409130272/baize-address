import os
from pydantic import BaseModel
import uvicorn
from fastapi import FastAPI
# import jionlp as jio
from datetime import datetime
import logging
import time
from lcparser import LocationParser
app = FastAPI()
current_date = datetime.now().date()
jio = LocationParser()

# 1、设置全局的日志格式和级别
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
                    datefmt='%m/%d/%Y %H:%M:%S',
                    level=logging.INFO)
logger = logging.getLogger(__name__)# __name__内置变量模块名称，轻松地识别出哪个模块产生了哪些日志消息（主程序模块）
dir_path = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(f'{dir_path}/log'):
    os.mkdir(f'{dir_path}/log')

file_handler = logging.FileHandler(f'{dir_path}/log/my_log{current_date}.log') #指定日志文件名my_log.log，默认在当前目录下创建
# file_handler = logging.FileHandler(f'{dir_path}/log/my_log{current_date}.log') #指定日志文件名my_log.log，默认在当前目录下创建
file_handler.setLevel(logging.INFO) # 设置日志级别(只输出对应级别INFO的日志信息)
file_handler.setFormatter(
logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s', '%m/%d/%Y %H:%M:%S'))
# 4、添加文件处理器到logger
logger.addHandler(file_handler)

@app.get("/")
def read_root():
    return {"Hello": "地址解析测试"}

class Item(BaseModel):
    address: str

#
# class People(BaseModel):  # 继承了BaseModel，定义了People的数据格式
#     name: str = None  # 默认了name的值为None
#     age: int = 18  # 默认了age为18
#     sex: str = "renyao"  # 默认了sex为renyao



@app.post("/analysis/")
async def get_address_analysis(item: Item):
    address = item.address
    logger.info(f'本次解析的地址：{address}')
    # print(f'本次解析的地址：{address}')
    ts = time.time()
    old_dict = jio(address, town_village=True)
    statueCode = '200'
    code = 'SUCCESS'
    desc = '地址解析成功'
    try:
        areacode = old_dict['code']
    except Exception as e:
        areacode = '000000'
        desc = '地址解析存疑，无法匹配正确的areacode'
        statueCode = '500'
        code = 'ERROR'

    if old_dict['province'] == None or old_dict['city'] == None or old_dict['county'] == None:
        # areacode = '000000'
        desc = '地址解析存疑，无法匹配正确的省或市/区'
        statueCode = '201'
        code = 'ERROR'

    analysis_address = {
        'provinceCode': areacode[0:2] + '0000',
        'provinceName': old_dict['province'],
        'cityCode': areacode[0:4] + '00',
        'CityName': old_dict['city'],
        'countyCode': areacode,
        'CountyName': old_dict['county'],
        'fullLocation': old_dict['full_location'],
        'origLocation': old_dict['orig_location'],
        'town': old_dict['town'],
        'village': old_dict['village'],
    }
    final_result = {
        'statueCode': statueCode,
        'desc': desc,
        'code': code,
        'data': analysis_address,
    }
    logger.info(f'本次地址解析消费时间:{time.time()-ts:.2f}s')
    return final_result


if __name__ == "__main__":
    # uvicorn.run(app='address_api:app', host='0.0.0.0', port=8500, reload=True, workers=8)
    uvicorn.run(app='address_api:app', host='0.0.0.0', port=8500, workers=2)
    # uvicorn.run(app='address_api:app', host='0.0.0.0', port=8500)
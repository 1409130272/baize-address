import json
import time
import requests
from multiprocessing import Process, Value, Pool
# xxx = requests.get('http://127.0.0.1:8100', timeout=5)
# print(xxx.text)

def mutipro_test():
    ts = time.time()
    # xx = requests.post('http://127.0.0.1:8200/analysis/', json={'address':'江苏省无锡市滨湖区蠡湖街道蠡湖家园c区14号302'})
    # xx2 = requests.post('http://127.0.0.1:8200/analysis/', json={'address':'滨湖区蠡湖街道蠡湖家园c区14号302'})
    xx2 = requests.post('http://192.168.16.133:8200/analysis/', json={'address':'滨湖区蠡湖街道蠡湖家园c区14号302'})
    # print(xx.status_code)
    # print(xx.text)
    print(xx2.text)
    cityname = json.loads(xx2.content.decode('utf-8'))['data']['CityName']
    print(cityname)
    # print(time.time()-ts)




if __name__ == '__main__':
    # process_num = 20
    tss = time.time()
    # for pro in range(process_num):
    #     # p = Process(target=consumer, args=(is_run,))
    #     p = Process(target=mutipro_test, args=())
    #     p.start()
    #
    #
    # print(time.time()-tss)
    # # mutipro_test()

    p = Pool(1)
    for pro in range(1):
        print(f'第{pro}进程开启')
        p.apply_async(mutipro_test, args=())
    p.close()
    p.join()
    # run()
    print(f"程序2 地址解析测试 运行结束  耗时：{time.time() - tss}")
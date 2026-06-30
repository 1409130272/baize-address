#!/bin/bash
#
#python /common/main/pop_task_callback.py
#python /common/main/push_task_callback.py
#find /data/taxdeclare/crawler-tax/ -name '*.log' | grep -v .git | awk '{print $1}' | xargs rm -rf
#find /data/taxdeclare/crawler-tax/ -name '*.log.*' | grep -v .git | awk '{print $1}' | xargs rm -rf
#var=`ps -ef|grep "task_run_bank" |grep -v 'grep'|awk '{print $2}'`
#if [ -n "$var" ];then
#  kill -15 $var
#fi
#var=`ps -ef|grep "compensated_task_callback" |grep -v 'grep'|awk '{print $2}'`
#if [ -n "$var" ];then
#  kill -15 $var
#fi
# 查找端口的进程ID
var=`ps -ef|grep "address_api" |grep -v 'grep'|awk '{print $2}'`
if [ -n "$var" ];then
  kill -15 $var
fi
current_dir=/home/ssdl/ins-address-py

if [ ! -d "$current_dir/log" ];then
    echo "create folder succeed";
      mkdir "$current_dir/log" ;
else
  echo "folder already exists" ;
fi

source /data/taxvenv/second_server/bin/activate
#nohup python /data/jiexifuwu/bank_pdf_receipt/common/main/task_consumer.py > /data/jiexifuwu/log/task_consumer.log 2>&1 &
#nohup python /data/jiexifuwu/bank_pdf_receipt/common/main/task_callback.py > /data/jiexifuwu/log/task_callback.log 2>&1 &
nohup python $current_dir/address_api.py > $current_dir/log/main_log.log 2>&1 &
echo 'start_success'
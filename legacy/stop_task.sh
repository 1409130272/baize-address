#!/bin/bash
function check_process_state()
{
while true
do
    var=`ps -ef | grep "$1" | grep -v 'grep' | awk '{print $8}'`
    if [ -z "$var" ];then
        break
    fi
    for p_name in $var
        do
            sleep 2
            echo -e "\033[31m stopping ${p_name} ... \033[0m"
        done
done
}
source /data/taxvenv/second_server/bin/activate
var=`ps -ef|grep "address_api" |grep -v 'grep'|awk '{print $2}'`
if [ -n "$var" ];then
  kill -15 $var
fi
#var=`ps -ef|grep "compensated_task_callback" |grep -v 'grep'|awk '{print $2}'`
#if [ -n "$var" ];then
#  kill -15 $var
#fi
# 查找端口的进程ID
#var=`ps -ef|grep "api_test" |grep -v 'grep'|awk '{print $2}'`
#if [ -n "$var" ];then
#  kill -15 $var
#fi
check_process_state "address_api"
#check_process_state "compensated_task_callback"
#check_process_state "api_test"
#nohup python /data/jiexifuwu/bank_pdf_receipt/clean_log.py &> /data/jiexifuwu/clean_log.log
echo 'stop success'
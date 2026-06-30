# import jionlp as jio
# print(jio.__version__)  # 查看 jionlp 的版本
# dir(jio)
# print(jio.extract_parentheses.__doc__)
from lcparser import LocationParser

# print(jio.parse_id_card('320211199612300414'))
# add = '孟津城关镇桂花大道427号'
add_right = '孟津城关镇桂花社区桂花大道427号'
add_wrong = '孟津城关镇大华社区桂花大道427号'
jio = LocationParser()

# print(add_right)
# print(jio.parse_location(add_right, town_village=True))
#
# print(add_wrong)
# print(jio.parse_location(add_wrong, town_village=True))
new_address = '海南省白沙黎族自治县 '
# new_address = '扬州市邢江区槐泗镇凯勒路29号'
# new_address = '邓州市张楼乡科郑中心小学'
# new_address = '静安区灵石路656号'
jio = LocationParser()
old_dict = jio(new_address, town_village=True)
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

if old_dict['province'] == None or old_dict['city'] == None:
    areacode = '000000'
    desc = '地址解析存疑，无法匹配正确的省或市'
    statueCode = '500'
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
print(final_result)
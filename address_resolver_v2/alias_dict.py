PROVINCE_ALIAS = {
    "北京市": ["北京"],
    "广西壮族自治区": ["广西"],
    "内蒙古自治区": ["内蒙古"],
    "宁夏回族自治区": ["宁夏"],
    "新疆维吾尔自治区": ["新疆"],
    "西藏自治区": ["西藏"],
    "香港特别行政区": ["香港"],
    "澳门特别行政区": ["澳门"],
    "河北省": ["冀"],
    "山西省": ["晋"],
    "辽宁省": ["辽"],
    "吉林省": ["吉"],
    "黑龙江省": ["黑"],
    "江苏省": ["苏"],
    "浙江省": ["浙"],
    "安徽省": ["皖"],
    "福建省": ["闽"],
    "江西省": ["赣"],
    "山东省": ["鲁"],
    "河南省": ["豫"],
    "湖北省": ["鄂"],
    "湖南省": ["湘"],
    "广东省": ["粤"],
    "海南省": ["琼"],
    "四川省": ["川", "蜀"],
    "贵州省": ["黔", "贵"],
    "云南省": ["滇", "云"],
    "陕西省": ["陕", "秦"],
    "甘肃省": ["甘", "陇"],
    "青海省": ["青"],
    "台湾省": ["台"],
}

CITY_ALIAS = {
    "广州市": ["广州"],
    "深圳市": ["深圳"],
    "杭州市": ["杭州"],
    "南京市": ["南京"],
    "成都市": ["成都"],
    "武汉市": ["武汉"],
    "西安市": ["西安"],
    "重庆市": ["重庆"],
    "上海市": ["上海"],
    "天津市": ["天津"],
    "哈尔滨市": ["哈尔滨"],
    "长春市": ["长春"],
    "沈阳市": ["沈阳"],
    "大连市": ["大连"],
    "青岛市": ["青岛"],
    "济南市": ["济南"],
    "郑州市": ["郑州"],
    "长沙市": ["长沙"],
    "福州市": ["福州"],
    "厦门市": ["厦门"],
    "昆明市": ["昆明"],
    "贵阳市": ["贵阳"],
    "南宁市": ["南宁"],
    "海口市": ["海口"],
    "太原市": ["太原"],
    "合肥市": ["合肥"],
    "南昌市": ["南昌"],
    "石家庄市": ["石家庄"],
    "呼和浩特市": ["呼和浩特"],
    "乌鲁木齐市": ["乌鲁木齐"],
    "拉萨市": ["拉萨"],
    "银川市": ["银川"],
    "西宁市": ["西宁"],
    "兰州市": ["兰州"],
    "台北市": ["台北"],
}

COUNTY_ALIAS = {
    "经济技术开发区": ["经开区"],
    "高新技术产业开发区": ["高新区", "高新技术开发区"],
    "经济技术开发区": ["经开区"],
    "滨海新区": ["滨海"],
    "浦东新区": ["浦东"],
    "两江新区": ["两江"],
    "天府新区": ["天府"],
    "雄安新区": ["雄安"],
    "金普新区": ["金普"],
    "贵安新区": ["贵安"],
    "西咸新区": ["西咸"],
    "赣江新区": ["赣江"],
    "江北新区": ["江北"],
}

PROVINCE_SUFFIXES = ["自治区", "特别行政区", "省", "市"]
CITY_SUFFIXES = ["自治州", "地区", "盟", "新区", "市"]
COUNTY_SUFFIXES = ["自治旗", "自治县", "特区", "林区", "新区", "区", "县", "市", "旗"]

ADMIN_SUFFIX_SKIP_CHARS = set("区县市旗省州盟")

import re

_AUTONOMOUS_COUNTY_PATTERN = re.compile(
    r'^(.+?)((?:土家族|苗族|彝族|藏族|羌族|回族|蒙古族|壮族|侗族|瑶族|满族|仡佬族|仫佬族|毛南族|京族|水族|布依族|朝鲜族|白族|哈尼族|傣族|傈僳族|佤族|畲族|高山族|拉祜族|东乡族|纳西族|景颇族|柯尔克孜|土族|达斡尔族|仫佬族|布朗族|撒拉族|毛南族|伦佬族|锡伯族|阿昌族|普米族|塔吉克族|怒族|乌孜别克族|俄罗斯族|鄂温克族|德昂族|保安族|裕固族|京族|塔塔尔族|独龙族|鄂伦春族|赫哲族|门巴族|珞巴族|基诺族)+)自治县$'
)

ETHNIC_FRAGMENTS = [
    "土家族", "土家", "苗族", "彝族", "藏族", "羌族", "回族", "蒙古族", "蒙古",
    "壮族", "侗族", "瑶族", "满族", "仡佬族", "仫佬族", "毛南族", "毛南", "京族",
    "水族", "布依族", "布依", "朝鲜族", "朝鲜", "白族", "哈尼族", "哈尼", "傣族",
    "傈僳族", "傈僳", "佤族", "畲族", "高山族", "高山", "拉祜族", "拉祜", "东乡族",
    "东乡", "纳西族", "纳西", "景颇族", "景颇", "柯尔克孜", "达斡尔族", "达斡尔",
    "布朗族", "布朗", "撒拉族", "撒拉", "伦佬族", "锡伯族", "锡伯", "阿昌族", "阿昌",
    "普米族", "普米", "塔吉克族", "塔吉克", "怒族", "乌孜别克族", "乌孜别克",
    "俄罗斯族", "俄罗斯", "鄂温克族", "鄂温克", "德昂族", "德昂", "保安族", "保安",
    "裕固族", "裕固", "塔塔尔族", "塔塔尔", "独龙族", "独龙", "鄂伦春族", "鄂伦春",
    "赫哲族", "赫哲", "门巴族", "门巴", "珞巴族", "珞巴", "基诺族", "基诺",
]
ETHNIC_FRAGMENTS = [f for f in ETHNIC_FRAGMENTS if len(f) >= 2]
ETHNIC_FRAGMENTS.sort(key=len, reverse=True)

ADMIN_WORDS = ["自治县", "自治州", "自治区", "自治旗", "特别行政区"]
ADMIN_WORDS.sort(key=len, reverse=True)


def make_short_name(name, level):
    if level in ("city", "county") and name.endswith("自治县"):
        m = _AUTONOMOUS_COUNTY_PATTERN.match(name)
        if m:
            core = m.group(1)
            if core and core != name:
                return core
    if level == "province":
        for suffix in PROVINCE_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                return name[: -len(suffix)]
        return name
    if level == "city":
        for suffix in CITY_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                return name[: -len(suffix)]
        return name
    if level == "county":
        for suffix in COUNTY_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                return name[: -len(suffix)]
        return name
    return name


def get_aliases(name, level):
    aliases = []
    if level == "province":
        aliases.extend(PROVINCE_ALIAS.get(name, []))
    elif level == "city":
        aliases.extend(CITY_ALIAS.get(name, []))
    elif level == "county":
        aliases.extend(COUNTY_ALIAS.get(name, []))
    short = make_short_name(name, level)
    if short and short != name and short not in aliases:
        aliases.append(short)
    return aliases

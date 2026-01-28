/**
 * Deep Vision 前端配置文件
 *
 * 此文件包含前端可配置的选项，方便后期维护和修改。
 */

const SITE_CONFIG = {
    // ============ 诗句轮播配置 ============
    quotes: {
        // 是否启用诗句轮播
        enabled: true,

        // 轮播间隔时间（毫秒）
        interval: 5000,  // 5秒

        // 诗句列表
        items: [
            {
                text: '路漫漫其修远兮，吾将上下而求索',
                source: '——屈原《离骚》'
            },
            {
                text: '问渠那得清如许，为有源头活水来',
                source: '——朱熹《观书有感》'
            },
            {
                text: '千里之行始于足下，万象之理源于细微',
                source: '——老子《道德经》'
            },
            {
                text: '博学之，审问之，慎思之，明辨之，笃行之',
                source: '——《礼记·中庸》'
            },
            {
                text: '纸上得来终觉浅，绝知此事要躬行',
                source: '——陆游《冬夜读书示子聿》'
            },
            {
                text: '知之者不如好之者，好之者不如乐之者',
                source: '——孔子《论语·雍也》'
            },
            {
                text: '水下80%，才是真相',
                source: ''
            },
            {
                text: '浮冰之上是表象，深渊之下是答案',
                source: ''
            },
            {
                text: '穿透表象，直抵核心',
                source: ''
            },
            {
                text: '看不见的，决定看得见的',
                source: ''
            }
        ]
    },

    // ============ 主题颜色配置 ============
    colors: {
        // 主强调色（鼠尾草蓝）
        primary: '#357BE2',

        // 成功状态色
        success: '#22C55E',

        // 进度条完成色（与 primary 保持一致）
        progressComplete: '#357BE2'
    },

    // ============ API 配置 ============
    api: {
        // API 基础地址
        baseUrl: 'http://localhost:5001/api',

        // Web Search 状态轮询间隔（毫秒）
        webSearchPollInterval: 200
    },

    // ============ 版本信息 ============
    // 版本信息从 version.json 动态加载
    version: {
        // 版本号（初始值，会被 version.json 覆盖）
        current: '1.3.2',

        // 版本信息文件路径
        configFile: 'version.json'
    }
};

// 如果在 Node.js 环境中，导出配置
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SITE_CONFIG;
}

/**
 * Deep Vision 前端配置文件
 *
 * 此文件由管理员中心维护。
 * 修改后请刷新浏览器页面生效。
 */

const SITE_CONFIG = {
  "quotes": {
    "enabled": true,
    "interval": 5000,
    "items": [
      {
        "text": "路漫漫其修远兮，吾将上下而求索",
        "source": "——屈原《离骚》"
      },
      {
        "text": "问渠那得清如许，为有源头活水来",
        "source": "——朱熹《观书有感》"
      },
      {
        "text": "千里之行始于足下，万象之理源于细微",
        "source": "——老子《道德经》"
      },
      {
        "text": "博学之，审问之，慎思之，明辨之，笃行之",
        "source": "——《礼记·中庸》"
      },
      {
        "text": "纸上得来终觉浅，绝知此事要躬行",
        "source": "——陆游《冬夜读书示子聿》"
      },
      {
        "text": "知之者不如好之者，好之者不如乐之者",
        "source": "——孔子《论语·雍也》"
      },
      {
        "text": "水下80%，才是真相",
        "source": ""
      },
      {
        "text": "浮冰之上是表象，深渊之下是答案",
        "source": ""
      },
      {
        "text": "穿透表象，直抵核心",
        "source": ""
      },
      {
        "text": "看不见的，决定看得见的",
        "source": ""
      },
      {
        "text": "心之所向，身之所往，命之所在",
        "source": "——许辉"
      },
      {
        "text": "桃李不言，下自成蹊",
        "source": "——《史记·李将军列传》"
      },
      {
        "text": "Singularity is coming, AI is faith.",
        "source": "——奇点将至，AI 即信仰"
      },
      {
        "text": "People don't know what they want until you show it to them.",
        "source": "——乔布斯"
      },
      {
        "text": "我们的任务是去读懂那些尚未写在页面上的东西",
        "source": "——亨利·福特"
      }
    ]
  },
  "colors": {
    "primary": "#357BE2",
    "success": "#22C55E",
    "progressComplete": "#357BE2"
  },
  "designTokens": {
    "light": {
      "colors": {
        "brand": "#357BE2",
        "brandHover": "#2563EB",
        "textPrimary": "#0F172A",
        "textSecondary": "#475569",
        "textMuted": "#64748B",
        "surface": "#FFFFFF",
        "surfaceSecondary": "#F8FAFC",
        "border": "#E2E8F0",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "danger": "#EF4444",
        "overlay": "rgba(15, 23, 42, 0.5)"
      }
    },
    "dark": {
      "colors": {
        "brand": "#5C98FF",
        "brandHover": "#78B1FF",
        "textPrimary": "#E6EDF5",
        "textSecondary": "#B7C4D4",
        "textMuted": "#95A3B6",
        "surface": "#1F242C",
        "surfaceSecondary": "#151A21",
        "border": "#3A4655",
        "success": "#4ADE80",
        "warning": "#FACC15",
        "danger": "#FB7185",
        "overlay": "rgba(3, 8, 18, 0.66)"
      }
    },
    "radius": {
      "sm": "0.5rem",
      "md": "0.75rem",
      "lg": "1rem",
      "xl": "1.25rem"
    },
    "spacing": {
      "compact": "0.5rem",
      "base": "0.75rem",
      "comfortable": "1rem",
      "spacious": "1.5rem"
    },
    "shadow": {
      "card": "0 8px 24px rgba(15, 23, 42, 0.08)",
      "modal": "0 26px 64px rgba(15, 23, 42, 0.28)",
      "focus": "0 0 0 3px rgba(53, 123, 226, 0.2)"
    },
    "zIndex": {
      "dropdown": 40,
      "modal": 50,
      "toast": 60,
      "guide": 70
    }
  },
  "visualPresets": {
    "default": "rational",
    "locked": true,
    "options": {
      "rational": {
        "label": "科技理性",
        "light": {
          "colors": {
            "brand": "#357BE2",
            "brandHover": "#2563EB",
            "overlay": "rgba(15, 23, 42, 0.5)"
          },
          "shadow": {
            "card": "0 8px 24px rgba(15, 23, 42, 0.08)",
            "modal": "0 26px 64px rgba(15, 23, 42, 0.28)"
          }
        },
        "dark": {
          "colors": {
            "brand": "#5C98FF",
            "brandHover": "#78B1FF",
            "overlay": "rgba(3, 8, 18, 0.66)"
          },
          "shadow": {
            "card": "0 10px 30px rgba(1, 7, 17, 0.34)",
            "modal": "0 30px 66px rgba(1, 4, 10, 0.62)"
          }
        }
      }
    }
  },
  "motion": {
    "durations": {
      "fast": 140,
      "base": 180,
      "slow": 240,
      "progress": 420
    },
    "easing": {
      "standard": "cubic-bezier(0.2, 0, 0, 1)",
      "emphasized": "cubic-bezier(0.2, 0.8, 0.2, 1)"
    },
    "reducedMotion": {
      "disableTypingEffect": true,
      "disableNonEssentialPulse": true
    }
  },
  "a11y": {
    "minContrastAA": 4.5,
    "focusRing": {
      "borderColorLight": "#357BE2",
      "borderColorDark": "#5C98FF",
      "ringColorLight": "rgba(53, 123, 226, 0.2)",
      "ringColorDark": "rgba(92, 152, 255, 0.22)",
      "ringStrongLight": "rgba(53, 123, 226, 0.42)",
      "ringStrongDark": "rgba(92, 152, 255, 0.48)",
      "underlayLight": "rgba(255, 255, 255, 0.92)",
      "underlayDark": "rgba(21, 27, 36, 0.96)"
    },
    "toast": {
      "atomic": true,
      "defaultLive": "polite",
      "errorLive": "assertive",
      "roleByType": {
        "success": "status",
        "info": "status",
        "warning": "alert",
        "error": "alert"
      }
    },
    "dialogs": {
      "showNewSessionModal": {
        "dialogId": "dv-dialog-new-session",
        "titleId": "dv-dialog-new-session-title",
        "descId": "dv-dialog-new-session-desc",
        "initialFocus": "[data-guide='guide-topic']",
        "returnFocus": "[data-guide='guide-new-session']"
      },
      "showCustomScenarioModal": {
        "dialogId": "dv-dialog-custom-scenario",
        "titleId": "dv-dialog-custom-scenario-title",
        "descId": "dv-dialog-custom-scenario-desc",
        "initialFocus": "#customScenarioName"
      },
      "showAiGenerateModal": {
        "dialogId": "dv-dialog-ai-generate",
        "titleId": "dv-dialog-ai-generate-title",
        "descId": "dv-dialog-ai-generate-desc",
        "initialFocus": "#aiScenarioDescription"
      },
      "showAiPreviewModal": {
        "dialogId": "dv-dialog-ai-preview",
        "titleId": "dv-dialog-ai-preview-title",
        "descId": "dv-dialog-ai-preview-desc",
        "initialFocus": "#aiGeneratedScenarioName"
      },
      "showMilestoneModal": {
        "dialogId": "dv-dialog-milestone",
        "titleId": "dv-dialog-milestone-title",
        "descId": "dv-dialog-milestone-desc"
      },
      "showDeleteModal": {
        "dialogId": "dv-dialog-delete-session",
        "titleId": "dv-dialog-delete-session-title",
        "descId": "dv-dialog-delete-session-desc"
      },
      "showRestartModal": {
        "dialogId": "dv-dialog-restart-session",
        "titleId": "dv-dialog-restart-session-title",
        "descId": "dv-dialog-restart-session-desc"
      },
      "showDeleteDocModal": {
        "dialogId": "dv-dialog-delete-doc",
        "titleId": "dv-dialog-delete-doc-title",
        "descId": "dv-dialog-delete-doc-desc"
      },
      "showDeleteReportModal": {
        "dialogId": "dv-dialog-delete-report",
        "titleId": "dv-dialog-delete-report-title",
        "descId": "dv-dialog-delete-report-desc"
      },
      "showSettingsModal": {
        "dialogId": "dv-dialog-settings",
        "titleId": "dv-dialog-settings-title",
        "descId": "dv-dialog-settings-desc",
        "initialFocus": "#dv-settings-tab-appearance"
      },
      "showBindPhoneModal": {
        "dialogId": "dv-dialog-bind-phone",
        "titleId": "dv-dialog-bind-phone-title",
        "descId": "dv-dialog-bind-phone-desc",
        "initialFocus": "#bind-phone-input"
      },
      "showActionConfirmModal": {
        "dialogId": "dv-dialog-action-confirm",
        "titleId": "dv-dialog-action-confirm-title",
        "descId": "dv-dialog-action-confirm-desc"
      },
      "showBatchDeleteModal": {
        "dialogId": "dv-dialog-batch-delete",
        "titleId": "dv-dialog-batch-delete-title",
        "descId": "dv-dialog-batch-delete-desc"
      },
      "showChangelogModal": {
        "dialogId": "dv-dialog-changelog",
        "titleId": "dv-dialog-changelog-title",
        "descId": "dv-dialog-changelog-desc"
      }
    }
  },
  "theme": {
    "defaultMode": "system"
  },
  "api": {
    "baseUrl": "http://localhost:5001/api",
    "webSearchPollInterval": 200
  },
  "researchTips": [
    "回答越具体，生成的问题越精准",
    "尝试用实例来描述你的经历",
    "越坦诚的回答越有助于深入访谈",
    "可以结合实际使用场景来作答",
    "详细描述痛点，会帮助发现更深层需求",
    "如果有相关文档，上传参考资料会加速分析",
    "别忘了表达你期望解决的核心问题",
    "用数据说话比空泛描述更有说服力",
    "思考一下\"为什么\"比\"是什么\"更重要",
    "描述目标用户的典型一天会很有帮助",
    "列举现有方案的不足能发现真实需求",
    "说明预期的成功标准让目标更清晰",
    "提及相关的约束条件避免方案偏离",
    "分享过往的失败经验同样有价值",
    "从用户视角而非功能视角思考问题",
    "优先级排序能帮助聚焦核心需求",
    "量化的指标比模糊的期望更易实现",
    "描述完整的业务流程有助理解全局",
    "对比竞品能发现差异化机会",
    "技术选型的理由比技术本身更重要",
    "预算和时间限制需要提前说明",
    "用户反馈的具体案例很有参考价值",
    "描述异常场景和边界条件很关键",
    "关键利益相关方的诉求需要平衡",
    "说明可接受的权衡取舍更务实",
    "复杂问题可以先拆解再逐个说明",
    "举例说明\"最好的情况\"和\"最坏的情况\"",
    "说明需求的紧急程度和重要程度",
    "多说\"具体遇到什么问题\"少说\"需要什么功能\"",
    "频率和规模数据能帮助判断优先级"
  ],
  "version": {
    "current": "1.26.0",
    "configFile": "version.json"
  },
  "presentation": {
    "enabled": true
  },
  "solution": {
    "enabled": true
  }
};

// 如果在 Node.js 环境中，导出配置
if (typeof module !== "undefined" && module.exports) {
  module.exports = SITE_CONFIG;
}

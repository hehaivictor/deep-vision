(function (global) {
    function cloneDefaultValue(value) {
        if (Array.isArray(value)) {
            return value.map((item) => cloneDefaultValue(item));
        }
        if (value && typeof value === 'object') {
            return Object.fromEntries(
                Object.entries(value).map(([key, item]) => [key, cloneDefaultValue(item)])
            );
        }
        return value;
    }

    const adminCenterStateDefaults = {
        opsMetrics: null,
        opsMetricsLoading: false,
        opsMetricsError: '',
        opsMetricsLastUpdatedAt: 0,
        opsMetricsLastLoadedAt: 0,
        opsMetricsLastN: 200,
        adminTab: 'overview',
        adminSummariesInfo: null,
        adminSummariesLoading: false,
        adminSummariesError: '',
        adminOwnershipTargetQuery: '',
        adminOwnershipTargetResults: [],
        adminOwnershipSourceQuery: '',
        adminOwnershipSourceResults: [],
        adminOwnershipSearchLoading: false,
        adminOwnershipForm: {
            to_user_id: '',
            to_account: '',
            scope: 'unowned',
            from_user_id: '',
            from_account: '',
            kinds: ['sessions', 'reports'],
            max_examples: 20,
        },
        adminOwnershipAudit: null,
        adminOwnershipAuditLoading: false,
        adminOwnershipAuditError: '',
        adminOwnershipPreview: null,
        adminOwnershipPreviewLoading: false,
        adminOwnershipPreviewError: '',
        adminOwnershipConfirmText: '',
        adminOwnershipApplyLoading: false,
        adminOwnershipHistory: [],
        adminOwnershipHistoryLoading: false,
        adminOwnershipHistoryError: '',
        adminConfigCenter: null,
        adminConfigLoading: false,
        adminConfigError: '',
        adminConfigSource: 'env',
        adminConfigSearch: '',
        adminConfigShowSecrets: false,
        adminConfigShowAdvanced: false,
        adminConfigActiveGroupId: {
            env: '',
            config: '',
            site: '',
        },
        adminConfigDraft: {
            env: {},
            config: {},
            site: {},
        },
        adminConfigSavingKey: '',
    };

    const adminCenterStateMethods = {
        resetAdminCenterModuleState() {
            Object.entries(adminCenterStateDefaults).forEach(([key, value]) => {
                this[key] = cloneDefaultValue(value);
            });
        },

        openAdminCenter(tab = 'overview') {
            if (!this.canViewAdminCenter()) return;
            this.showAccountMenu = false;
            this.showSettingsModal = false;
            this.switchView('admin');
            this.switchAdminTab(tab);
        },

        switchAdminTab(tab = 'overview') {
            if (!this.canViewAdminCenter()) return;
            const allowedTabs = ['overview', 'license', 'ops', 'summaries', 'ownership', 'config'];
            const normalizedTab = allowedTabs.includes(tab) ? tab : 'overview';
            this.adminTab = normalizedTab;
            void this.ensureAdminDataForTab(normalizedTab);
        },

        async ensureAdminDataForTab(tab = this.adminTab) {
            if (!this.canViewAdminCenter()) return;
            if (tab === 'overview') {
                await this.loadAdminOverview();
                return;
            }
            if (tab === 'license') {
                this.adminLicenseBootstrapForm = {
                    ...this.createDefaultAdminLicenseBootstrapForm(),
                    ...this.adminLicenseBootstrapForm,
                    duration_days: this.normalizePositiveIntInput(
                        this.adminLicenseBootstrapForm?.duration_days,
                        this.createDefaultAdminLicenseBootstrapForm().duration_days,
                    ),
                };
                await this.loadAdminLicenseBootstrapStatus({ silent: true });
                this.adminLicenseGenerateForm = {
                    ...this.createDefaultAdminLicenseGenerateForm(),
                    ...this.adminLicenseGenerateForm,
                    duration_days: this.normalizePositiveIntInput(
                        this.adminLicenseGenerateForm?.duration_days,
                        this.createDefaultAdminLicenseGenerateForm().duration_days,
                    ),
                };
                if (this.canManageAdminLicenses()) {
                    await Promise.all([
                        this.loadAdminLicenseSummary(),
                        this.loadAdminLicenseList({ page: this.adminLicensePagination.page || 1 }),
                    ]);
                } else {
                    this.adminLicenseSummaryError = this.adminLicenseBootstrapStatus?.eligible
                        ? '当前账号尚未绑定有效 License，可先创建并绑定首个种子 License。'
                        : '当前账号需先绑定有效 License，才能进入 License 管理。';
                    this.adminLicenseList = [];
                    this.adminLicenseDetail = null;
                    this.adminLicenseEvents = [];
                }
                return;
            }
            if (tab === 'ops') {
                await this.loadOpsMetrics({ force: !this.opsMetrics });
                return;
            }
            if (tab === 'summaries') {
                await this.loadAdminSummariesInfo();
                return;
            }
            if (tab === 'ownership') {
                await this.loadAdminOwnershipHistory();
                return;
            }
            if (tab === 'config') {
                await this.loadAdminConfigCenter();
            }
        },

        async loadAdminOverview() {
            const tasks = [
                this.loadOpsMetrics({ silent: true }),
                this.loadAdminSummariesInfo({ silent: true }),
                this.loadAdminOwnershipHistory({ silent: true }),
            ];
            if (this.canManageAdminLicenses()) {
                tasks.push(this.loadAdminLicenseSummary({ silent: true }));
            }
            await Promise.all(tasks);
        },

        async loadAdminSummariesInfo(options = {}) {
            const { silent = false } = options;
            if (!this.canViewAdminCenter()) return null;
            this.adminSummariesLoading = true;
            this.adminSummariesError = '';
            try {
                const payload = await this.apiCall('/summaries', { skipAuthRedirect: true });
                this.adminSummariesInfo = payload && typeof payload === 'object' ? payload : null;
                return this.adminSummariesInfo;
            } catch (error) {
                const message = error?.message || '摘要缓存信息加载失败';
                this.adminSummariesError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.adminSummariesLoading = false;
            }
        },

        async clearAdminSummariesCache() {
            if (!this.canViewAdminCenter()) return;
            const confirmed = await this.openActionConfirmDialog({
                title: '确认清空摘要缓存',
                message: '该操作会删除当前全部智能摘要缓存，但不会删除会话和报告数据。',
                tone: 'warning',
                confirmText: '确认清空',
            });
            if (!confirmed) return;
            try {
                const payload = await this.apiCall('/summaries/clear', {
                    method: 'POST',
                    body: JSON.stringify({}),
                    skipAuthRedirect: true,
                });
                await this.loadAdminSummariesInfo({ silent: true });
                this.showToast(payload?.message || '摘要缓存已清空', 'success');
            } catch (error) {
                this.showToast(error?.message || '摘要缓存清空失败', 'error');
            }
        },

        syncAdminConfigDraftFromPayload(payload = null) {
            const nextDraft = {
                env: {},
                config: {},
                site: {},
            };
            ['env', 'config', 'site'].forEach((source) => {
                const groups = Array.isArray(payload?.[source]?.groups) ? payload[source].groups : [];
                groups.forEach((group) => {
                    const groupId = String(group?.id || '').trim();
                    if (!groupId) return;
                    nextDraft[source][groupId] = {};
                    const items = Array.isArray(group?.items) ? group.items : [];
                    items.forEach((item) => {
                        const key = String(item?.key || '').trim();
                        if (!key) return;
                        nextDraft[source][groupId][key] = String(item?.value ?? '');
                    });
                });
            });
            this.adminConfigDraft = nextDraft;
        },

        getAdminConfigRequestErrorMessage(error, fallback = '配置中心加载失败') {
            if (Number(error?.status) === 404) {
                return '当前运行中的后端未包含配置中心接口，请重启服务或部署最新后端版本后再试';
            }
            return error?.message || fallback;
        },

        normalizeAdminConfigSource(source = this.adminConfigSource) {
            return source === 'config' || source === 'site' ? source : 'env';
        },

        setAdminConfigSource(source = 'env') {
            this.adminConfigSource = this.normalizeAdminConfigSource(source);
            this.ensureAdminConfigActiveGroup(this.adminConfigSource);
        },

        getAdminConfigSourceMeta(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            return this.adminConfigCenter?.meta?.source_meta?.[normalized] || {};
        },

        getAdminConfigSourceLabel(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            if (normalized === 'config') return 'config.py';
            if (normalized === 'site') return '共享前端配置';
            return '.env';
        },

        async loadAdminConfigCenter(options = {}) {
            const { silent = false } = options;
            if (!this.canViewAdminCenter()) return null;
            this.adminConfigLoading = true;
            this.adminConfigError = '';
            try {
                const payload = await this.apiCall('/admin/config-center', {
                    skipAuthRedirect: true,
                });
                this.adminConfigCenter = payload && typeof payload === 'object' ? payload : null;
                this.syncAdminConfigDraftFromPayload(this.adminConfigCenter);
                ['env', 'config', 'site'].forEach((source) => this.ensureAdminConfigActiveGroup(source));
                return this.adminConfigCenter;
            } catch (error) {
                const message = this.getAdminConfigRequestErrorMessage(error, '配置中心加载失败');
                this.adminConfigError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.adminConfigLoading = false;
            }
        },

        getAdminConfigSourcePayload(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            return this.adminConfigCenter?.[normalized] || { file: {}, groups: [] };
        },

        normalizeAdminConfigSearchText(value = '') {
            return String(value || '')
                .toLowerCase()
                .normalize('NFKC')
                .replace(/\s+/g, ' ')
                .trim();
        },

        compactAdminConfigSearchText(value = '') {
            return this.normalizeAdminConfigSearchText(value).replace(/[\s_\-./:@]+/g, '');
        },

        isAdminConfigSubsequenceMatch(text = '', keyword = '') {
            if (!keyword) return true;
            let cursor = 0;
            for (const char of String(text || '')) {
                if (char === keyword[cursor]) {
                    cursor += 1;
                    if (cursor >= keyword.length) {
                        return true;
                    }
                }
            }
            return false;
        },

        matchesAdminConfigSearchValue(value = '', keyword = this.adminConfigSearch) {
            const normalizedValue = this.normalizeAdminConfigSearchText(value);
            const normalizedKeyword = this.normalizeAdminConfigSearchText(keyword);
            if (!normalizedKeyword) return true;
            if (!normalizedValue) return false;
            if (normalizedValue.includes(normalizedKeyword)) return true;
            const compactValue = this.compactAdminConfigSearchText(normalizedValue);
            const compactKeyword = this.compactAdminConfigSearchText(normalizedKeyword);
            if (!compactKeyword) return true;
            if (compactValue.includes(compactKeyword)) return true;
            return this.isAdminConfigSubsequenceMatch(compactValue, compactKeyword);
        },

        matchesAdminConfigSearchParts(parts = [], keyword = this.adminConfigSearch) {
            const normalizedKeyword = this.normalizeAdminConfigSearchText(keyword);
            if (!normalizedKeyword) return true;
            const tokens = normalizedKeyword.split(' ').filter(Boolean);
            if (tokens.length === 0) return true;
            return tokens.every((token) => (
                parts.some((part) => this.matchesAdminConfigSearchValue(part, token))
            ));
        },

        getAdminConfigVisibleGroups(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            const payload = this.getAdminConfigSourcePayload(normalized);
            const groups = Array.isArray(payload?.groups) ? payload.groups : [];
            const showAdvanced = !!this.adminConfigShowAdvanced;
            return groups
                .map((group) => {
                    const items = Array.isArray(group?.items) ? group.items : [];
                    const visibleScopeItems = showAdvanced ? items : items.filter(item => !item?.advanced);
                    const visibleItems = visibleScopeItems.filter((item) => this.matchesAdminConfigSearchParts([
                        group?.title,
                        group?.description,
                        item?.label,
                        item?.key,
                        item?.description,
                        item?.placeholder,
                    ]));
                    return {
                        ...group,
                        visibleItems,
                        visibleItemCount: visibleItems.length,
                        totalItemCount: visibleScopeItems.length,
                    };
                })
                .filter((group) => Array.isArray(group.visibleItems) && group.visibleItems.length > 0);
        },

        ensureAdminConfigActiveGroup(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            const groups = this.getAdminConfigVisibleGroups(normalized);
            if (!groups.length) {
                this.adminConfigActiveGroupId[normalized] = '';
                return '';
            }
            const currentId = String(this.adminConfigActiveGroupId?.[normalized] || '');
            if (groups.some((group) => String(group?.id || '') === currentId)) {
                return currentId;
            }
            const nextId = String(groups[0]?.id || '');
            this.adminConfigActiveGroupId[normalized] = nextId;
            return nextId;
        },

        getAdminConfigCurrentGroupId(source = this.adminConfigSource) {
            return this.ensureAdminConfigActiveGroup(source);
        },

        setAdminConfigActiveGroup(source, groupId) {
            const normalized = this.normalizeAdminConfigSource(source);
            this.adminConfigActiveGroupId[normalized] = String(groupId || '');
        },

        getAdminConfigActiveGroup(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            const groups = this.getAdminConfigVisibleGroups(normalized);
            const currentId = this.ensureAdminConfigActiveGroup(normalized);
            return groups.find((group) => String(group?.id || '') === String(currentId || '')) || null;
        },

        getAdminConfigDraftValue(source, groupId, key) {
            const normalizedSource = this.normalizeAdminConfigSource(source);
            return String(this.adminConfigDraft?.[normalizedSource]?.[groupId]?.[key] ?? '');
        },

        setAdminConfigDraftValue(source, groupId, key, value) {
            const normalizedSource = this.normalizeAdminConfigSource(source);
            if (!this.adminConfigDraft[normalizedSource]) {
                this.adminConfigDraft[normalizedSource] = {};
            }
            if (!this.adminConfigDraft[normalizedSource][groupId]) {
                this.adminConfigDraft[normalizedSource][groupId] = {};
            }
            this.adminConfigDraft[normalizedSource][groupId][key] = String(value ?? '');
        },

        getAdminConfigInputType(item = {}) {
            const fieldType = String(item?.type || 'text').trim();
            if (fieldType === 'integer' || fieldType === 'float') return 'number';
            if (item?.secret) return this.adminConfigShowSecrets ? 'text' : 'password';
            return 'text';
        },

        isAdminConfigGroupSaving(source, groupId) {
            return this.adminConfigSavingKey === `${source}:${groupId}`;
        },

        async saveAdminConfigGroup(source, groupId) {
            if (!this.canViewAdminCenter()) return;
            const normalizedSource = this.normalizeAdminConfigSource(source);
            const groups = Array.isArray(this.adminConfigCenter?.[normalizedSource]?.groups)
                ? this.adminConfigCenter[normalizedSource].groups
                : [];
            const targetGroup = groups.find((group) => String(group?.id || '') === String(groupId || ''));
            if (!targetGroup) {
                this.showToast('未找到配置分组', 'error');
                return;
            }
            const values = {};
            const items = Array.isArray(targetGroup?.items) ? targetGroup.items : [];
            items.forEach((item) => {
                const key = String(item?.key || '').trim();
                if (!key) return;
                values[key] = this.getAdminConfigDraftValue(normalizedSource, targetGroup.id, key);
            });
            this.adminConfigSavingKey = `${normalizedSource}:${targetGroup.id}`;
            try {
                const payload = await this.apiCall('/admin/config-center/save', {
                    method: 'POST',
                    body: JSON.stringify({
                        source: normalizedSource,
                        group_id: targetGroup.id,
                        values,
                    }),
                    skipAuthRedirect: true,
                });
                this.adminConfigCenter = payload?.config_center && typeof payload.config_center === 'object'
                    ? payload.config_center
                    : this.adminConfigCenter;
                this.syncAdminConfigDraftFromPayload(this.adminConfigCenter);
                this.showToast(payload?.message || '配置已保存', 'success');
            } catch (error) {
                this.showToast(this.getAdminConfigRequestErrorMessage(error, '配置保存失败'), 'error');
            } finally {
                this.adminConfigSavingKey = '';
            }
        },

        async searchAdminUsers(target = 'target') {
            if (!this.canViewAdminCenter()) return;
            const isSource = target === 'source';
            const query = String(isSource ? this.adminOwnershipSourceQuery : this.adminOwnershipTargetQuery || '').trim();
            this.adminOwnershipSearchLoading = true;
            try {
                const params = new URLSearchParams();
                if (query) {
                    params.set('q', query);
                }
                params.set('limit', '12');
                const payload = await this.apiCall(`/admin/users?${params.toString()}`, {
                    skipAuthRedirect: true,
                });
                const items = Array.isArray(payload?.items) ? payload.items : [];
                if (isSource) {
                    this.adminOwnershipSourceResults = items;
                } else {
                    this.adminOwnershipTargetResults = items;
                }
                return items;
            } catch (error) {
                this.showToast(error?.message || '用户搜索失败', 'error');
                return [];
            } finally {
                this.adminOwnershipSearchLoading = false;
            }
        },

        selectAdminOwnershipUser(user, target = 'target') {
            const normalizedUser = user && typeof user === 'object' ? user : null;
            if (!normalizedUser) return;
            const isSource = target === 'source';
            if (isSource) {
                this.adminOwnershipForm.from_user_id = String(normalizedUser.id || '');
                this.adminOwnershipForm.from_account = String(normalizedUser.account || normalizedUser.phone || normalizedUser.email || '').trim();
                this.adminOwnershipSourceQuery = this.adminOwnershipForm.from_account;
                this.adminOwnershipSourceResults = [];
                return;
            }
            this.adminOwnershipForm.to_user_id = String(normalizedUser.id || '');
            this.adminOwnershipForm.to_account = String(normalizedUser.account || normalizedUser.phone || normalizedUser.email || '').trim();
            this.adminOwnershipTargetQuery = this.adminOwnershipForm.to_account;
            this.adminOwnershipTargetResults = [];
        },

        toggleAdminOwnershipKind(kind = '') {
            const normalized = String(kind || '').trim();
            if (!normalized) return;
            const nextKinds = Array.isArray(this.adminOwnershipForm?.kinds)
                ? [...this.adminOwnershipForm.kinds]
                : [];
            if (nextKinds.includes(normalized)) {
                this.adminOwnershipForm.kinds = nextKinds.filter(item => item !== normalized);
                return;
            }
            this.adminOwnershipForm.kinds = [...nextKinds, normalized];
        },

        buildAdminOwnershipPayload() {
            const kinds = Array.isArray(this.adminOwnershipForm?.kinds)
                ? this.adminOwnershipForm.kinds.filter(item => item === 'sessions' || item === 'reports')
                : [];
            return {
                to_user_id: this.adminOwnershipForm?.to_user_id ? Number(this.adminOwnershipForm.to_user_id) : undefined,
                to_account: String(this.adminOwnershipForm?.to_account || this.adminOwnershipTargetQuery || '').trim(),
                scope: String(this.adminOwnershipForm?.scope || 'unowned').trim() || 'unowned',
                from_user_id: this.adminOwnershipForm?.scope === 'from-user' && this.adminOwnershipForm?.from_user_id
                    ? Number(this.adminOwnershipForm.from_user_id)
                    : undefined,
                kinds,
                max_examples: Math.max(1, Math.min(50, Number(this.adminOwnershipForm?.max_examples) || 20)),
            };
        },

        async auditAdminOwnership() {
            const targetUserId = Number(this.adminOwnershipForm?.to_user_id) || 0;
            const userAccount = String(this.adminOwnershipForm?.to_account || '').trim();
            if (!targetUserId && !userAccount) {
                this.showToast('请先选择目标用户', 'warning');
                return;
            }
            this.adminOwnershipAuditLoading = true;
            this.adminOwnershipAuditError = '';
            try {
                const payload = await this.apiCall('/admin/ownership-migrations/audit', {
                    method: 'POST',
                    body: JSON.stringify({
                        user_id: targetUserId || undefined,
                        user_account: userAccount || undefined,
                        kinds: this.buildAdminOwnershipPayload().kinds,
                    }),
                    skipAuthRedirect: true,
                });
                this.adminOwnershipAudit = payload;
                return payload;
            } catch (error) {
                const message = error?.message || '归属审计失败';
                this.adminOwnershipAuditError = message;
                this.showToast(message, 'error');
                return null;
            } finally {
                this.adminOwnershipAuditLoading = false;
            }
        },

        async previewAdminOwnershipMigration() {
            const payload = this.buildAdminOwnershipPayload();
            if (!payload.to_user_id && !payload.to_account) {
                this.showToast('请先选择目标用户', 'warning');
                return;
            }
            if (!Array.isArray(payload.kinds) || payload.kinds.length === 0) {
                this.showToast('请至少选择一种迁移对象', 'warning');
                return;
            }
            if (payload.scope === 'from-user' && !payload.from_user_id) {
                this.showToast('scope=from-user 时必须选择来源用户', 'warning');
                return;
            }
            this.adminOwnershipPreviewLoading = true;
            this.adminOwnershipPreviewError = '';
            this.adminOwnershipConfirmText = '';
            try {
                const result = await this.apiCall('/admin/ownership-migrations/preview', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                    skipAuthRedirect: true,
                });
                this.adminOwnershipPreview = result;
                this.showToast('dry-run 预览已生成，请确认后再正式迁移', 'success');
                return result;
            } catch (error) {
                const message = error?.message || 'dry-run 预览失败';
                this.adminOwnershipPreviewError = message;
                this.showToast(message, 'error');
                return null;
            } finally {
                this.adminOwnershipPreviewLoading = false;
            }
        },

        canApplyAdminOwnershipMigration() {
            const preview = this.adminOwnershipPreview;
            if (!preview || typeof preview !== 'object') return false;
            const confirmPhrase = String(preview.confirm_phrase || '').trim();
            return !!confirmPhrase && String(this.adminOwnershipConfirmText || '').trim() === confirmPhrase && !this.adminOwnershipApplyLoading;
        },

        async applyAdminOwnershipMigration() {
            if (!this.canApplyAdminOwnershipMigration()) {
                this.showToast('请先完成 dry-run，并输入正确确认词', 'warning');
                return;
            }
            const preview = this.adminOwnershipPreview || {};
            const payload = {
                ...this.buildAdminOwnershipPayload(),
                preview_token: preview.preview_token,
                confirm_text: String(this.adminOwnershipConfirmText || '').trim(),
            };
            this.adminOwnershipApplyLoading = true;
            try {
                const result = await this.apiCall('/admin/ownership-migrations/apply', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                    skipAuthRedirect: true,
                });
                this.adminOwnershipPreview = null;
                this.adminOwnershipConfirmText = '';
                await Promise.all([
                    this.loadAdminOwnershipHistory({ silent: true }),
                    this.auditAdminOwnership(),
                ]);
                this.showToast('归属迁移已执行', 'success');
                return result;
            } catch (error) {
                this.showToast(error?.message || '归属迁移失败', 'error');
                return null;
            } finally {
                this.adminOwnershipApplyLoading = false;
            }
        },

        async loadAdminOwnershipHistory(options = {}) {
            const { silent = false } = options;
            if (!this.canViewAdminCenter()) return [];
            this.adminOwnershipHistoryLoading = true;
            this.adminOwnershipHistoryError = '';
            try {
                const payload = await this.apiCall('/admin/ownership-migrations?limit=50', {
                    skipAuthRedirect: true,
                });
                this.adminOwnershipHistory = Array.isArray(payload?.items) ? payload.items : [];
                return this.adminOwnershipHistory;
            } catch (error) {
                const message = error?.message || '迁移历史加载失败';
                this.adminOwnershipHistoryError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return [];
            } finally {
                this.adminOwnershipHistoryLoading = false;
            }
        },

        async rollbackAdminOwnershipMigration(backupId = '') {
            const normalizedBackupId = String(backupId || '').trim();
            if (!normalizedBackupId) return;
            const confirmed = await this.openActionConfirmDialog({
                title: '确认回滚迁移',
                message: `将按备份 ${normalizedBackupId} 恢复归属关系，是否继续？`,
                tone: 'danger',
                confirmText: '确认回滚',
            });
            if (!confirmed) return;
            try {
                const payload = await this.apiCall('/admin/ownership-migrations/rollback', {
                    method: 'POST',
                    body: JSON.stringify({ backup_id: normalizedBackupId }),
                    skipAuthRedirect: true,
                });
                await Promise.all([
                    this.loadAdminOwnershipHistory({ silent: true }),
                    this.auditAdminOwnership(),
                ]);
                this.showToast(payload?.backup_id ? `已回滚 ${payload.backup_id}` : '迁移已回滚', 'success');
            } catch (error) {
                this.showToast(error?.message || '回滚失败', 'error');
            }
        },

        formatBytes(bytes = 0) {
            const value = Number(bytes) || 0;
            if (value <= 0) return '0 B';
            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
            const size = value / (1024 ** exponent);
            return `${size.toFixed(size >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
        },

        getAdminOwnershipKindsLabel(kinds = []) {
            const values = Array.isArray(kinds) ? kinds : [];
            const labels = values.map(item => item === 'sessions' ? '会话' : (item === 'reports' ? '报告' : '')).filter(Boolean);
            return labels.length > 0 ? labels.join('、') : '未指定';
        },

        async loadOpsMetrics(options = {}) {
            const {
                force = false,
                silent = false
            } = options;
            if (!this.canViewOpsMetrics()) {
                return null;
            }
            if (this.opsMetricsLoading && !force) {
                return this.opsMetrics;
            }

            const now = Date.now();
            if (!force && this.opsMetrics && (now - (Number(this.opsMetricsLastLoadedAt) || 0)) < 15000) {
                return this.opsMetrics;
            }

            this.opsMetricsLoading = true;
            this.opsMetricsError = '';
            try {
                const lastN = Math.max(50, Number(this.opsMetricsLastN) || 200);
                const result = await this.apiCall(`/metrics?last_n=${lastN}`, {
                    suppressErrorLog: true,
                    expectedStatuses: [403]
                });
                this.opsMetrics = result && typeof result === 'object' ? result : {};
                this.opsMetricsLastUpdatedAt = Date.now();
                this.opsMetricsLastLoadedAt = this.opsMetricsLastUpdatedAt;
                return this.opsMetrics;
            } catch (error) {
                const message = error?.status === 403 ? '仅管理员可查看运行监控' : (error?.message || '监控数据加载失败');
                this.opsMetricsError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.opsMetricsLoading = false;
            }
        },

        refreshOpsMetricsIfVisible(options = {}) {
            if (!this.canViewOpsMetrics()) {
                return;
            }
            if (!(this.currentView === 'admin' && this.adminTab === 'ops')) {
                return;
            }
            void this.loadOpsMetrics({
                force: true,
                silent: true,
                ...options
            });
        },

        getOpsMetricsFreshnessText() {
            const updatedAt = Number(this.opsMetricsLastUpdatedAt) || 0;
            if (!updatedAt) return '尚未加载';
            const deltaSeconds = Math.max(0, Math.floor((Date.now() - updatedAt) / 1000));
            if (deltaSeconds < 5) return '刚刚更新';
            if (deltaSeconds < 60) return `${deltaSeconds} 秒前更新`;
            const deltaMinutes = Math.floor(deltaSeconds / 60);
            if (deltaMinutes < 60) return `${deltaMinutes} 分钟前更新`;
            return this.formatDate(updatedAt);
        },
    };

    function attach(app) {
        if (!app || typeof app !== 'object') return app;

        Object.entries(adminCenterStateDefaults).forEach(([key, value]) => {
            if (typeof app[key] === 'undefined') {
                app[key] = cloneDefaultValue(value);
            }
        });

        Object.assign(app, adminCenterStateMethods);
        return app;
    }

    global.DeepVisionAdminCenterStateModule = { attach };
})(window);

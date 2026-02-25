/**
 * 政策API调用封装（过渡层）
 * 已委托到统一客户端 window.MarketApp.api
 */

const PolicyAPI = {
  baseURL: '/api/v1/policies',

  async request(url, options = {}) {
    if (!window.MarketApp || !window.MarketApp.api) {
      throw new Error('MarketApp.api 未初始化，请先加载 /static/js/app-shell.js');
    }
    const method = (options.method || 'GET').toUpperCase();
    return window.MarketApp.api.request(method, url, options);
  },

  async requestFull(url, options = {}) {
    if (!window.MarketApp || !window.MarketApp.api) {
      throw new Error('MarketApp.api 未初始化，请先加载 /static/js/app-shell.js');
    }
    const method = (options.method || 'GET').toUpperCase();
    return window.MarketApp.api.requestFull(method, url, options);
  },

  async listPolicies(params = {}) {
    const queryParams = new URLSearchParams();

    if (params.state) queryParams.append('state', params.state);
    if (params.policy_type) queryParams.append('policy_type', params.policy_type);
    if (params.status) queryParams.append('status', params.status);
    if (params.start) queryParams.append('start', params.start);
    if (params.end) queryParams.append('end', params.end);
    if (params.page) queryParams.append('page', params.page);
    if (params.page_size) queryParams.append('page_size', params.page_size);
    if (params.sort_by) queryParams.append('sort_by', params.sort_by);
    if (params.sort_order) queryParams.append('sort_order', params.sort_order);

    return this.requestFull(`${this.baseURL}?${queryParams}`);
  },

  async getStats(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.start) queryParams.append('start', params.start);
    if (params.end) queryParams.append('end', params.end);
    return this.request(`${this.baseURL}/stats?${queryParams}`);
  },

  async getStatePolicies(state, params = {}) {
    const queryParams = new URLSearchParams();
    if (params.start) queryParams.append('start', params.start);
    if (params.end) queryParams.append('end', params.end);
    return this.request(`${this.baseURL}/state/${state}?${queryParams}`);
  },

  async getPolicyDetail(policyId) {
    return this.request(`${this.baseURL}/${policyId}`);
  }
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = PolicyAPI;
}

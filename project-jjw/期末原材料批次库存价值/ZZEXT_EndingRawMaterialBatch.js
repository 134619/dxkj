class LowcodeComponent extends Component {
  constructor() {
    this.searchForm = 'queryForm001'
  }
  state = {
    btnCol: 24,
    colSpan: 4,
    condition: {},
    dataSource: [],
    columns: [],
    page: {
      "page_size": 10,
      "page_num": 1,
      "page_sum": 1,
      "data_sum": 1
    },
    _payload_: {
      page: {
        "page_size": 10,
        "page_num": 1,
        "page_sum": 1,
        "data_sum": 1
      },
    },
    nestDisplay: [],
    loading: false,
    plantList: [], // 工厂
    storLocCodeLIst: [], // 库存地点
    dlLoading: false
  }
  componentDidMount() {
    this.clacBtnColWidth()
    this.init()
  }
  componentWillUnmount() {
    this.destroyMes()
  }
  // 计算按钮对应的列
  clacBtnColWidth(width = this.state.colSpan) {
    if (width) {
      this.setState({
        colSpan: width
      })
    }
    const colNum = Object.values(this.$(this.searchForm)?.getFieldsValue())?.length
    const defaultColWidth = width || 4
    const inRowNum = Math.floor(24 / defaultColWidth)
    const btnCol = 24 - defaultColWidth * (colNum % inRowNum)
    this.setState({ btnCol })
  }

  genPeriod() {
    this.setState({
      periodList: new Array(12).fill(0).map((m, i) => ({
        label: (i + 1 + '').padStart(2, 0),
        value: (i + 1 + '').padStart(2, 0)
      }))
    })
  }

  getCurrentDateTimeString() {
    const currentDate = new Date();
    const year = currentDate.getFullYear();
    const month = String(currentDate.getMonth() + 1).padStart(2, '0');
    const day = String(currentDate.getDate()).padStart(2, '0');
    const hours = String(currentDate.getHours()).padStart(2, '0');
    const minutes = String(currentDate.getMinutes()).padStart(2, '0');
    const seconds = String(currentDate.getSeconds()).padStart(2, '0');
    return `${year}${month}${day}${hours}${minutes}${seconds}`;
  }


  // 生成uuid
  generateUUID() {
    const objectURL = URL.createObjectURL(new Blob());
    const result = objectURL.slice(-36).replace(/-/g, '');
    URL.revokeObjectURL(objectURL);
    return result;
  }

  // 添加唯一值id
  genernateId(arr, key = 'id') {
    return arr.map((item, index) => ({
      ...item,
      [key]: this.generateUUID()
    }))
  }


  // 接收[a,b] [{a}, {b}], 只传 labelName 说明 label和value 一致, 默认拼接label value
  formatLabelValue(arr, labelName, valueName = '', isCompose = true) {
    let value = valueName ? valueName : labelName;
    const compose = labelName && valueName && isCompose;

    return arr.map(item => {
      const name = window._.isObject(item) ? (compose ? `${item[value]} ${item[labelName]}` : item[labelName]) : item
      const id = window._.isObject(item) ? item[value] : item
      return {
        ...(window._.isObject(item) ? item : {}),
        label: name,
        value: id,
        name,
        id

      }
    })
  }

  // 转化columns
  formatColumns(arr, labelName = 'description', valueName = 'field') {
    return arr.map(item => {
      const title = item[labelName];
      const dataIndex = item[valueName]
      return {
        ...item,
        title,
        dataIndex,
        name: dataIndex
      }
    })
  }
  formatDate(date, format = 'YYYY-MM-DD') {
    return window.moment(date).format(format)
  }

  pickData(obj, props) {
    return window._.pick(obj, props)
  }
  omitData(obj, props) {
    return window._.omit(obj, props)
  }

  // 下载
  download(url, data, fileName, loadingName = 'dlLoading') {
    this.setState({
      [loadingName]: true
    })
    const timeString = this.getCurrentDateTimeString()
    window.downloadFile(url, {
      data,
      fileName: `${fileName}${timeString}.xlsx`
    }).then(res => {
      if (!res || res?.msg) this.errTip(res?.msg || '文件下载失败')
    }).finally(() => {
      this.setState({
        [loadingName]: false
      })
    })
  }
  sucTip(msg) {
    if (!msg) return;
    this.utils.message.success(msg)
  }

  errTip(msg, type = 'error', message = '错误消息') {
    if (!msg) return;
    this.utils.notification[type]({
      message,
      description: msg,
      duration: null
    })
  }

  // 处理接口返回值
  parseRes(options) {
    const { res, tipType = 'error', isTip = false, errTip = true, errDeal = false, message } = options;
    if (res?.code === 200) {
      isTip && this.sucTip(res.msg);
      return res;
    } else {
      errTip && this.errTip(res?.msg || '服务器错误!', tipType, message)
      return errDeal ? res : false
    }
  }


  // 全局销毁提示
  destroyMes() {
    this.utils.notification.destroy()
  }
  // py接口封装
  getPYLoad(params, isTip = false) {
    return new Promise((resolve, reject) => {
      this.dataSourceMap.extension.load(params).then(res => {
        const result = this.parseRes({ res, isTip })
        if (result) {
          resolve(result)
        } else {
          reject()
        }
      })
    })
  }

  // 处理select数据
  querySelectData(options) {
    const {
      url,
      data = {},
      label,
      value = '',
      stateName,
      isCompose = true
    } = options;
    this.dataSourceMap[url].load(data).then(res => {
      const result = this.parseRes({ res })
      if (result) {
        const data = result.data || [];
        this.setState({
          [stateName]: this.formatLabelValue(data, label, value, isCompose)
        })
      }
    })
  }

  // #endregion
  // ---------------------------业务代码-------------------------

  init() {
    this.genPeriod()
    this.getPlant()
    this.getStorLocCode()
  }

  // 获取工厂代码
  getPlant() {
    this.querySelectData({
      url: 'extension',
      data: {
        "target_script": "OSSearchHelp",
        "target_func": "getPlantData"
      },
      label: 'plant_description',
      value: 'plant_code',
      stateName: 'plantList'
    })
  }
  // 获取库存地点
  getStorLocCode() {
    this.querySelectData({
      url: 'extension',
      data: {
        "target_script": "OSSearchHelp",
        "target_func": "getStorLocCode"
      },
      label: 'stor_loc_desc',
      value: 'stor_loc_code',
      stateName: 'storLocCodeLIst'
    })
  }
  onFinish(values) {
    const params = {
      ...values,
      year: this.formatDate(values.year, 'YYYY'),
    }
    this.setState({
      condition: params
    })
    this.query(params)
  }


  // 查询
  query(data) {
    try {
      let { _payload_ } = this.state
      _payload_.page = {
        "page_size": 0,
        "page_num": 1,
        "page_sum": 0,
        "data_sum": 0
      }
      this.setState({ loading: true })
      this.getPYLoad({
        "target_script": "ZZEXT_EndingRawMaterialBatch",
        "target_func": "get_ending_raw_material_batch",
        _payload_,
        data
      }).then(res => {
        res = this.parseRes({ res })
        const dataSource = res.data || []
        const columns = this.formatColumns(res.display)
        const page = res.page
        const nestDisplay = res.title_display
        this.$('vtable-44eb33e4').setData({ data: res?.data || [], display: res?.display || [] })
        this.setState({
          dataSource,
          columns,
          page,
          nestDisplay
        })
      }).finally(() => {
        this.setState({ loading: false })
      })
    } catch {
      this.setState({ loading: false })
    }


  }


  onDownload(data) {
    // 导出暂未开放: 后端为查询裸函数(无 @ResetResponse 装饰器), 暂不支持 Excel 导出
    // 先提示避免点击报错; 如需彻底隐藏, 在低代码设计器里移除/隐藏导出按钮即可
    this.errTip('导出功能暂未开放')
  }
  plantCodeOnChange(value, option) {
    // 工厂变更回调: 已移除成本版本联动(本报表无成本版本); 若设计器仍绑定此事件, 保留空壳避免调用缺失方法
  }
}
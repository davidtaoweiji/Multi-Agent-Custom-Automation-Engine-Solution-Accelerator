# PDF Upload Testing Guide

## 测试文件说明

`test_pdf_upload.py` - 测试 PDF 文件上传功能（仅测试 Step 1）

## 运行测试

### 1. 安装依赖（可选 - 用于生成真实 PDF）

```bash
pip install reportlab
```

如果不安装 `reportlab`，测试会使用最小的 PDF 占位符。

### 2. 运行测试

```bash
cd src/backend
python test_pdf_upload.py
```

## 测试内容

### Test 1: 单个 PDF 上传
- 创建一个包含发票信息的 PDF 文件
- 提交到 workflow
- 验证 PDF 文本被正确提取
- 检查发票数据是否被提取

### Test 2: 多个 PDF 上传
- 创建两个 PDF 文件
- 同时提交到 workflow
- 验证每个 PDF 被识别为独立的发票
- 检查是否提取了多个发票

## 测试的 PDF 内容示例

```
INVOICE
Invoice Number: INV-2025-001
Date: 2025-11-05

Vendor: Starbucks Coffee
Company: Microsoft Corporation
Tax ID: 91-1144442

Items:
  - Coffee and breakfast meal
  - Team meeting refreshments

Total Amount: $45.50 USD
```

## 预期输出

### 成功输出示例：
```
✅ PDF created: 1234 bytes
📝 STEP 1: Submit Invoice with PDF Attachment
State: CONFIRM (or VALIDATE)
📋 Extracted Invoice Data:
  Invoice #1:
    vendor_name: Starbucks Coffee
    company_name: Microsoft Corporation
    tax_id: 91-1144442
    total_amount: 45.50
    ...
✅ Step 1 PASSED - PDF processed successfully
```

## 故障排查

### 问题：`unhashable type: 'slice'` 错误
**原因：** `state["images"]` 包含字典而不是字节数组

**解决方案：** 确保在 `simple_chat_handler.py` 中正确提取 `data` 字段：
```python
image_bytes_list = [img["data"] for img in input_task.images]
```

### 问题：PDF 文本提取失败
**检查：**
1. 确保安装了 `pypdf` 包
2. 检查 PDF 文件是否有效
3. 查看日志中的详细错误信息

## 与现有测试的对比

| 测试文件 | 测试内容 | 步骤 |
|---------|---------|------|
| `test_handler_e2e.py` | 完整工作流（文本输入） | Step 1-4 |
| `test_pdf_upload.py` | PDF 文件上传 | Step 1 only |

## 下一步

要测试完整的 PDF workflow（包括修正和确认），可以扩展此测试添加 Step 2-4。

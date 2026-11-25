/**
 * Khảo sát HomeMatch AI Agent (thuê phòng trọ, studio, căn hộ tại TP.HCM và Hà Nội).
 *
 * Cách dùng: script.google.com → Dự án mới → dán toàn bộ file → chạy createHomeMatchSurvey().
 * Sau khi thu đủ câu trả lời, chạy exportForEval() để có file CSV đúng cột mà
 * `python -m eval survey-report --csv <file>` cần (respondent_id, sus1..sus6,
 * trust_explanation, satisfaction_suggestions, privacy_financial).
 */

var AGREE = ['Hoàn toàn không đồng ý', 'Hoàn toàn đồng ý'];

// Mã cột cho eval ↔ câu hỏi trên form. sus1/3/5 là câu tích cực, sus2/4/6 là câu tiêu cực.
var EVAL_ITEMS = {
  sus1: 'T1. Tôi muốn dùng HomeMatch mỗi khi cần tìm phòng.',
  sus2: 'T2. Tôi thấy HomeMatch phức tạp hơn mức cần thiết.',
  sus3: 'T3. Tôi thấy HomeMatch dễ sử dụng.',
  sus4: 'T4. Tôi cần người hướng dẫn mới dùng được HomeMatch.',
  sus5: 'T5. Các chức năng (trò chuyện với AI, gợi ý phòng, chi phí, bản đồ, nhắn tin chủ nhà) liền mạch với nhau.',
  sus6: 'T6. Tôi phải tìm hiểu khá nhiều thứ trước khi dùng được HomeMatch.',
  trust_explanation: 'T7. Phần giải thích vì sao phòng được gợi ý giúp tôi tin vào danh sách.',
  satisfaction_suggestions: 'T8. Tôi hài lòng với những phòng HomeMatch gợi ý cho tôi.',
  privacy_financial: 'T9. Tôi yên tâm về cách HomeMatch giữ kín thông tin thu nhập và tài chính của tôi.'
};

function createHomeMatchSurvey() {
  var form = FormApp.create('Khảo sát nhu cầu thuê phòng và trải nghiệm HomeMatch AI Agent');
  form.setDescription(
    'Khảo sát phục vụ khóa luận tốt nghiệp về HomeMatch – nền tảng cho thuê phòng trọ, studio, căn hộ ' +
    'tại TP.HCM và Hà Nội, có trợ lý AI gợi ý phòng theo nhu cầu và khả năng chi trả của người thuê.\n' +
    'Khảo sát ẩn danh, không thu email, mất khoảng 3–4 phút. Cảm ơn bạn!'
  );
  form.setProgressBar(true);
  form.setCollectEmail(false);

  // ================= PHẦN 1: THÔNG TIN CHUNG =================
  var role = form.addMultipleChoiceItem()
    .setTitle('Q1. Bạn đang ở vai trò nào?')
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Q2. Độ tuổi của bạn?')
    .setChoiceValues(['Dưới 22 tuổi', '22–27 tuổi', '28–35 tuổi', '36–45 tuổi', 'Trên 45 tuổi'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Q3. Bạn đang thuê / cho thuê ở đâu?')
    .setChoiceValues(['TP. Hồ Chí Minh', 'Hà Nội', 'Tỉnh/thành khác'])
    .setRequired(true);

  // ================= PHẦN 2A: NGƯỜI THUÊ =================
  var renterPage = form.addPageBreakItem()
    .setTitle('Phần 2: Dành cho người thuê')
    .setHelpText('Nghĩ về lần tìm phòng gần nhất của bạn.');

  form.addMultipleChoiceItem()
    .setTitle('R1. Bạn thường thuê loại chỗ ở nào?')
    .setChoiceValues(['Phòng trọ', 'Studio / căn hộ dịch vụ', 'Căn hộ chung cư', 'Ở ghép'])
    .showOtherOption(true)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('R2. Tổng chi phí nhà ở mỗi tháng của bạn (tiền phòng + điện nước + phí dịch vụ)?')
    .setChoiceValues(['Dưới 3 triệu', '3 – 5 triệu', '5 – 8 triệu', '8 – 12 triệu', 'Trên 12 triệu'])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('R3. Bạn thường tìm phòng qua đâu? (Chọn nhiều)')
    .setChoiceValues([
      'Nhóm/trang Facebook',
      'Chợ Tốt, Batdongsan và các trang rao vặt',
      'Ứng dụng tìm phòng',
      'Người quen giới thiệu',
      'Đi xem biển "cho thuê phòng"',
      'Môi giới'
    ])
    .showOtherOption(true)
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('R4. Khó khăn lớn nhất khi tìm phòng là gì? (Chọn nhiều)')
    .setChoiceValues([
      'Tin đăng ảo, ảnh không giống thực tế, phòng đã cho thuê vẫn đăng',
      'Giá đăng không ghi rõ điện, nước, phí dịch vụ nên khó biết tổng tiền thật',
      'Mất nhiều thời gian lọc thủ công qua rất nhiều tin',
      'Khó biết phòng cách chỗ làm / trường bao xa, đi lại mất bao lâu',
      'Khó so sánh các phòng với nhau',
      'Khó tính trước tiền cọc và tiền cần có khi dọn vào',
      'Liên hệ chủ nhà chậm, hẹn xem phòng mất công'
    ])
    .showOtherOption(true)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('R5. Bạn mất bao lâu để chọn được 3–5 phòng đáng đi xem?')
    .setChoiceValues(['Dưới 1 giờ', 'Vài giờ', '1 – 3 ngày', 'Gần 1 tuần', 'Hơn 1 tuần'])
    .setRequired(true);

  form.addScaleItem()
    .setTitle('R6. Việc tự tính tổng chi phí hằng tháng và số tiền cần có khi dọn vào khó đến mức nào?')
    .setBounds(1, 5)
    .setLabels('Rất dễ', 'Rất khó')
    .setRequired(true);

  form.addGridItem()
    .setTitle('R7. Mức độ cần thiết của các tính năng sau (1 = Không cần, 5 = Rất cần)')
    .setRows([
      'Trò chuyện với AI để nói nhu cầu bằng lời thường, AI hỏi lại khi còn thiếu',
      'Gợi ý 5 phòng phù hợp nhất kèm lý do và điểm cần đánh đổi',
      'Ước tính tổng chi phí hằng tháng và tiền cần có khi dọn vào',
      'Bản đồ và quãng đường từ phòng tới chỗ làm / trường',
      'So sánh nhiều phòng cạnh nhau',
      'Nhắn tin chủ nhà và đặt lịch xem phòng (trực tiếp hoặc online) ngay trên ứng dụng',
      'Ghi nhớ sở thích của tôi cho lần tìm sau'
    ])
    .setColumns(['1', '2', '3', '4', '5'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('R8. Khi AI đã chọn xong phòng phù hợp, bạn muốn nhận danh sách thế nào?')
    .setChoiceValues([
      'Nhận ngay, tôi tự liên hệ chủ nhà để hỏi lại',
      'Chờ chủ nhà xác nhận phòng còn trống rồi mới nhận (có thể chờ vài giờ đến 1 ngày)',
      'Sao cũng được'
    ])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('R9. Điều gì khiến bạn tin dùng một trợ lý AI tìm phòng? (Chọn nhiều)')
    .setChoiceValues([
      'Thu nhập và thông tin tài chính không bị chia sẻ cho chủ nhà',
      'Giải thích rõ vì sao gợi ý phòng này',
      'Không ưu tiên tin trả phí hay tin mới đăng khi xếp hạng',
      'Ghi rõ khoản nào là ước tính, khoản nào là giá thật',
      'Thông tin phòng được cập nhật đúng (còn trống, giá mới)'
    ])
    .showOtherOption(true)
    .setRequired(true);

  // ================= PHẦN 2B: CHỦ NHÀ =================
  var landlordPage = form.addPageBreakItem()
    .setTitle('Phần 2: Dành cho chủ nhà / chủ trọ');

  form.addMultipleChoiceItem()
    .setTitle('L1. Bạn đang cho thuê bao nhiêu phòng / căn?')
    .setChoiceValues(['1 – 5', '6 – 15', '16 – 50', 'Trên 50'])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('L2. Bạn đang quản lý phòng cho thuê bằng gì? (Chọn nhiều)')
    .setChoiceValues(['Sổ tay', 'Excel / Google Sheets', 'Zalo / Facebook', 'Phần mềm quản lý nhà trọ'])
    .showOtherOption(true)
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('L3. Việc nào tốn công nhất với bạn? (Chọn nhiều)')
    .setChoiceValues([
      'Đăng tin và trả lời khách hỏi phòng',
      'Hẹn và dẫn khách đi xem phòng',
      'Làm hợp đồng',
      'Ghi chỉ số điện nước, tính và gửi hóa đơn',
      'Nhắc và theo dõi tiền thuê',
      'Xử lý sửa chữa, hỏng hóc',
      'Định giá phòng cho hợp lý'
    ])
    .showOtherOption(true)
    .setRequired(true);

  form.addGridItem()
    .setTitle('L4. Mức độ cần thiết của các tính năng sau (1 = Không cần, 5 = Rất cần)')
    .setRows([
      'Quản lý phòng, hợp đồng và người thuê ở một chỗ',
      'Nhập chỉ số điện nước và tự tạo hóa đơn',
      'Ghi nhận thanh toán, nhắc người thuê đến hạn',
      'Nhận và theo dõi yêu cầu sửa chữa',
      'AI viết sẵn bài đăng cho từng kênh (Facebook, Zalo…)',
      'Gợi ý giá thuê dựa trên các phòng tương tự gần đó'
    ])
    .setColumns(['1', '2', '3', '4', '5'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('L5. Bạn muốn biết về người thuê tiềm năng theo cách nào?')
    .setChoiceValues([
      'Chỉ khi họ nhắn tin hoặc hẹn xem phòng',
      'Muốn duyệt trước danh sách AI gợi ý cho từng người thuê',
      'Không quan trọng'
    ])
    .setRequired(true);

  // ================= PHẦN 3: ĐÃ DÙNG THỬ CHƯA =================
  var triedPage = form.addPageBreakItem().setTitle('Phần 3: Dùng thử HomeMatch');
  var tried = form.addMultipleChoiceItem()
    .setTitle('Bạn đã dùng thử bản demo HomeMatch chưa?')
    .setRequired(true);

  // ================= PHẦN 4: ĐÁNH GIÁ SAU DÙNG THỬ =================
  var trialPage = form.addPageBreakItem()
    .setTitle('Phần 4: Đánh giá sau khi dùng thử')
    .setHelpText('Chọn mức đồng ý với từng câu (1 = Hoàn toàn không đồng ý, 5 = Hoàn toàn đồng ý).');

  Object.keys(EVAL_ITEMS).forEach(function (key) {
    form.addScaleItem()
      .setTitle(EVAL_ITEMS[key])
      .setBounds(1, 5)
      .setLabels(AGREE[0], AGREE[1])
      .setRequired(true);
  });

  form.addParagraphTextItem()
    .setTitle('T10. Có chỗ nào khi dùng thử làm bạn khó hiểu hoặc thấy sai? (Không bắt buộc)')
    .setRequired(false);

  // ================= PHẦN 5: KẾT THÚC =================
  var finalPage = form.addPageBreakItem().setTitle('Phần 5: Mức độ sẵn sàng và góp ý');

  form.addMultipleChoiceItem()
    .setTitle('Q4. Bạn có sẵn sàng dùng HomeMatch khi tìm phòng / cho thuê lần tới không?')
    .setChoiceValues(['Chắc chắn có', 'Có thể sẽ thử', 'Cần cân nhắc thêm', 'Không có nhu cầu'])
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Q5. Góp ý hoặc mong muốn của bạn với trợ lý AI tìm phòng? (Không bắt buộc)')
    .setRequired(false);

  // ================= ĐIỀU HƯỚNG =================
  role.setChoices([
    role.createChoice('Đang thuê hoặc sắp thuê phòng / căn hộ', renterPage),
    role.createChoice('Sinh viên sắp đi thuê lần đầu', renterPage),
    role.createChoice('Chủ nhà / chủ trọ đang cho thuê', landlordPage)
  ]);
  landlordPage.setGoToPage(triedPage);   // người thuê làm xong Phần 2A thì bỏ qua Phần 2B
  tried.setChoices([
    tried.createChoice('Đã dùng thử', trialPage),
    tried.createChoice('Chưa dùng thử', finalPage)
  ]);

  var sheet = SpreadsheetApp.create('Kết quả khảo sát HomeMatch');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
  PropertiesService.getScriptProperties().setProperty('HOMEMATCH_FORM_ID', form.getId());

  Logger.log('Tạo form thành công.');
  Logger.log('Link chỉnh sửa: ' + form.getEditUrl());
  Logger.log('Link gửi khảo sát: ' + form.getPublishedUrl());
  Logger.log('Bảng kết quả: ' + sheet.getUrl());
}

/** Xuất câu trả lời Phần 4 ra CSV cho `python -m eval survey-report`. Chỉ lấy người đã dùng thử. */
function exportForEval() {
  var formId = PropertiesService.getScriptProperties().getProperty('HOMEMATCH_FORM_ID');
  if (!formId) throw new Error('Chưa có form. Chạy createHomeMatchSurvey() trước.');
  var keys = Object.keys(EVAL_ITEMS);
  var lines = [['respondent_id'].concat(keys).join(',')];
  var count = 0;
  FormApp.openById(formId).getResponses().forEach(function (response) {
    var byTitle = {};
    response.getItemResponses().forEach(function (r) {
      byTitle[r.getItem().getTitle()] = r.getResponse();
    });
    if (byTitle[EVAL_ITEMS.sus1] === undefined) return;   // chưa dùng thử
    count += 1;
    var id = 'S' + ('0' + count).slice(-2);
    lines.push([id].concat(keys.map(function (k) { return byTitle[EVAL_ITEMS[k]] || ''; })).join(','));
  });
  var file = DriveApp.createFile('homematch-survey-eval.csv', lines.join('\n'), MimeType.CSV);
  Logger.log('Đã xuất ' + count + ' người dùng thử: ' + file.getUrl());
}

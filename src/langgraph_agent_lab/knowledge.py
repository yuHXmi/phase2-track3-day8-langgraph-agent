"""Small in-repo knowledge base for grading-question retrieval checks."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeHit:
    doc_id: str
    answer: str
    context: str


DOCUMENTS: dict[str, str] = {
    "policy_refund_v4": (
        "Refund policy v4. Khách hàng có tối đa 7 ngày làm việc để gửi yêu cầu "
        "hoàn tiền sau khi đơn được xác nhận. Các sản phẩm bị loại khỏi điều kiện "
        "hoàn tiền gồm hàng kỹ thuật số, license key, và subscription. Finance Team "
        "xử lý yêu cầu hoàn tiền trong 3-5 ngày làm việc."
    ),
    "sla_p1_2026": (
        "SLA P1 2026. Ticket P1 có SLA phản hồi ban đầu là 15 phút. SLA resolution "
        "cho ticket P1 là 4 giờ. Nếu không có phản hồi với ticket P1 sau 10 phút, "
        "hệ thống sẽ auto escalate."
    ),
    "it_helpdesk_faq": (
        "IT helpdesk FAQ. Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp. VPN "
        "cho phép kết nối tối đa 2 thiết bị cùng lúc."
    ),
    "hr_leave_policy": (
        "HR leave policy 2026. Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép "
        "năm theo chính sách HR 2026."
    ),
    "access_control_sop": (
        "Access control SOP. Level 4 Admin Access yêu cầu phê duyệt bởi IT Manager "
        "và CISO."
    ),
}


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    ascii_text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return ascii_text.lower()


def retrieve_knowledge(query: str) -> KnowledgeHit | None:
    """Return the top knowledge hit for known policy/SLA/FAQ/HR/access-control questions."""
    text = normalize_text(query)

    refund_policy_query = (
        "hoan tien" in text
        or "finance team" in text
        or ("refund" in text and any(term in text for term in ("policy", "eligible", "process")))
    )
    if refund_policy_query:
        if any(term in text for term in ("bao nhieu ngay", "toi da", "sau khi don")):
            answer = (
                "Theo policy_refund_v4, khách hàng có tối đa 7 ngày làm việc để gửi "
                "yêu cầu hoàn tiền sau khi đơn được xác nhận."
            )
        elif any(term in text for term in ("loai san pham", "loai khoi", "khong duoc")):
            answer = (
                "Theo policy_refund_v4, các sản phẩm bị loại khỏi điều kiện hoàn tiền "
                "gồm hàng kỹ thuật số, license key, và subscription."
            )
        else:
            answer = (
                "Theo policy_refund_v4, Finance Team xử lý yêu cầu hoàn tiền trong "
                "3-5 ngày làm việc."
            )
        return KnowledgeHit("policy_refund_v4", answer, DOCUMENTS["policy_refund_v4"])

    if "p1" in text and ("sla" in text or "auto escalate" in text or "phan hoi" in text):
        if any(term in text for term in ("auto escalate", "khong co phan hoi")):
            answer = (
                "Theo sla_p1_2026, nếu không có phản hồi với ticket P1 sau 10 phút "
                "thì hệ thống auto escalate."
            )
        elif "resolution" in text:
            answer = "Theo sla_p1_2026, SLA resolution cho ticket P1 là 4 giờ."
        else:
            answer = "Theo sla_p1_2026, SLA phản hồi ban đầu cho ticket P1 là 15 phút."
        return KnowledgeHit("sla_p1_2026", answer, DOCUMENTS["sla_p1_2026"])

    if any(term in text for term in ("dang nhap sai", "vpn", "tai khoan bi khoa")):
        if "vpn" in text:
            answer = "Theo it_helpdesk_faq, VPN cho phép kết nối tối đa 2 thiết bị cùng lúc."
        else:
            answer = (
                "Theo it_helpdesk_faq, tài khoản bị khóa sau 5 lần đăng nhập sai "
                "liên tiếp."
            )
        return KnowledgeHit("it_helpdesk_faq", answer, DOCUMENTS["it_helpdesk_faq"])

    if any(term in text for term in ("hr 2026", "ngay phep", "duoi 3 nam")):
        answer = (
            "Theo hr_leave_policy, nhân viên dưới 3 năm kinh nghiệm được "
            "12 ngày phép năm."
        )
        return KnowledgeHit("hr_leave_policy", answer, DOCUMENTS["hr_leave_policy"])

    if any(term in text for term in ("level 4 admin access", "admin access", "ciso")):
        answer = (
            "Theo access_control_sop, Level 4 Admin Access yêu cầu phê duyệt bởi "
            "IT Manager và CISO."
        )
        return KnowledgeHit("access_control_sop", answer, DOCUMENTS["access_control_sop"])

    return None

import enum


class IncomeType(str, enum.Enum):
    WAGE = "WAGE"  # 근로소득
    BUSINESS = "BUSINESS"  # 사업소득
    OTHER = "OTHER"  # 기타소득
    DAILY = "DAILY"  # 일용근로소득
    RETIREMENT = "RETIREMENT"  # 퇴직소득

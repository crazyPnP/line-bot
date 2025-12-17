from repos.supabase_repo import SupabaseRepo
from domain.errors import NotAllowed, NotFound

class ProposalService:
    def __init__(self):
        self.repo = SupabaseRepo()

    def start_create_proposal(self, line_user_id: str) -> str:
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if profile["role"] != "student":
            raise NotAllowed("只有學生可以提案")

        return "請輸入：老師ID 時間 起訖 課程模式 內容"

    def accept_by_index(self, line_user_id: str, index: int) -> str:
        teacher = self.repo.get_profile_by_line_user_id(line_user_id)
        if teacher["role"] != "teacher":
            raise NotAllowed("只有老師可以接受提案")

        proposals = self.repo.list_pending_proposals(teacher["id"])
        if index < 1 or index > len(proposals):
            raise NotFound("找不到該提案")

        proposal = proposals[index - 1]

        booking_id = self.repo.rpc_accept_proposal(
            proposal_id=proposal["proposal_id"],
            teacher_id=teacher["id"]
        )

        return f"已接受提案，建立課程 {booking_id}"

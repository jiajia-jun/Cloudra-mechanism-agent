from cloudra.agent import Follower


class small_mol(Follower):
    id: str = 'a-4'
    name: str = 'small_mol'
    type: str = 'follower'
    prompt_name: str = 'small_mol'

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return True

    def script_run_permission(self) -> bool:
        return True

    def destructive_permission(self) -> bool:
        return True


def get_class():
    return small_mol

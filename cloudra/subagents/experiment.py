from cloudra.agent import Follower


class experiment(Follower):
    id: str = 'a-7'
    name: str = 'experiment'
    type: str = 'follower'
    prompt_name: str = 'experiment'

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        return True

    def script_run_permission(self) -> bool:
        return True

    def destructive_permission(self) -> bool:
        return True


def get_class():
    return experiment

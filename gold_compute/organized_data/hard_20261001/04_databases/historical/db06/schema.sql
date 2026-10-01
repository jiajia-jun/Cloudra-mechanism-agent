CREATE INDEX idx_compute_jobs_claim
    ON compute_jobs(state, lease_expires_at)
;

CREATE INDEX idx_compute_jobs_notify
    ON compute_jobs(state, notified_at)
;

CREATE TABLE compute_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        session_id TEXT,
        state TEXT,
        path TEXT,
        start_timestamp INTEGER,
        end_timestamp INTEGER DEFAULT -1,
        jobtype TEXT DEFAULT 'gaussian',
        -- 作业归属的注册节点（services/nodes.py 的 node_id）：容量按节点分池
        -- 记账的唯一依据；NULL 视为注册表的 default_node_id（旧行升级路径）。
        node_id TEXT,
        scheduler TEXT DEFAULT 'local',
        scheduler_options TEXT DEFAULT '{}',
        scheduler_job_id TEXT,
        scheduler_state TEXT,
        scheduler_script TEXT,
        last_error TEXT,
        lease_owner TEXT,
        lease_expires_at REAL,
        attempt_count INTEGER DEFAULT 0,
        -- 调度器：排队优先级与 agent 声明的资源申请（核心链路不解析输入文件）
        priority INTEGER NOT NULL DEFAULT 0,
        req_cpus INTEGER NOT NULL DEFAULT 1,
        req_memory_mb INTEGER,
        -- xtb 显式任务参数（xtb 是 CLI 标志驱动，.xyz 不携带这些语义）：
        -- submit 时校验入库，guard/Slurm 据此拼 --chrg/--uhf/--opt/--hess/
        -- --ohess/--alpb/--parallel，绝不回退裸单点
        charge INTEGER NOT NULL DEFAULT 0,
        multiplicity INTEGER NOT NULL DEFAULT 1,
        xtb_task TEXT NOT NULL DEFAULT 'sp',
        xtb_solvent TEXT,
        -- 观测/取证用进程号（存活判定的权威是 .cloudra/ 下的 flock，不读 PID）
        guard_pid INTEGER,
        calc_pid INTEGER,
        -- 完成通知投递标记（ComputeNotifyBroker 补投对账依据）
        notified_at REAL
    );

CREATE TABLE sqlite_sequence(name,seq);

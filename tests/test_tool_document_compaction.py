"""Re-readable contracts fold without losing mixed scientific outputs."""
import json

import pytest

from cloudra.runtime_v2.compaction import compact_context
from tests.test_runtime_v2_compaction_integrity import RecordingSummarizer


@pytest.mark.asyncio
async def test_host_document_message_folds_to_names_and_versions():
    summarizer=RecordingSummarizer()
    messages=[{'role':'system','content':'HUGE_UNIQUE_CONTRACT_BODY '*2000,
        'tool_documents':[{'name':'read','revision':'v1'}]},
        {'role':'user','content':'User quoted HUGE_UNIQUE_CONTRACT_BODY'}]
    _,stats=await compact_context(messages,head=[],notices=[],summarize=summarizer,
        context_window=200000,max_output=32000)
    assert stats['compacted']
    supplied=str(summarizer.calls)
    assert supplied.count('HUGE_UNIQUE_CONTRACT_BODY')==1
    assert 'read' in supplied
    assert 'v1' in supplied


def test_mixed_program_output_removes_only_actual_documents():
    from cloudra.tools import documentation
    assert hasattr(documentation,'compact_document_outputs'), 'Document provenance compaction is missing'
    doc={'name':'read','revision':'v1','content':'CONTRACT','references':[]}
    outputs=[[doc], {'energy':-42.5}, 'user text']
    compact=documentation.compact_document_outputs(outputs,[doc])
    assert 'CONTRACT' not in json.dumps(compact)
    assert compact[1]=={'energy':-42.5}
    assert compact[2]=='user text'

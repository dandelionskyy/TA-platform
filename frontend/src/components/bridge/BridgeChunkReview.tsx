import { useState, type FormEvent } from 'react';
import type { BridgeChunk, BridgeChunkType } from '../../services/bridgeApi';
import { useLanguage } from '../../i18n/LanguageContext';

const types: BridgeChunkType[] = ['UNREVIEWED', 'DEFINITION', 'EXAMPLE', 'HINT', 'PARTIAL_SOLUTION', 'WORKED_SOLUTION', 'ANSWER'];
const safe = new Set<BridgeChunkType>(['DEFINITION', 'EXAMPLE', 'HINT']);

export default function BridgeChunkReview({ chunks, busy, onSave }: {
  chunks: BridgeChunk[];
  busy: boolean;
  onSave: (chunk: BridgeChunk, type: BridgeChunkType, reviewed: boolean) => void;
}) {
  const { text } = useLanguage();
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? chunks : chunks.filter(chunk => !chunk.reviewed);
  const save = (event: FormEvent<HTMLFormElement>, chunk: BridgeChunk) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const type = String(values.get('chunk_type')) as BridgeChunkType;
    onSave(chunk, type, safe.has(type) && values.get('reviewed') === 'on');
  };
  return <div className="bridge-chunks">
    <p>{text('资料段需要人工分类。只有审核通过的定义、例子和提示可用于学生检索；答案段保持受限。', 'Classify each source chunk. Only reviewed definitions, examples and hints can enter student retrieval. Solution chunks remain restricted.')}</p>
    <label className="bridge-check"><input type="checkbox" checked={showAll} onChange={event => setShowAll(event.target.checked)} />{text('显示已审核的资料段', 'Show reviewed chunks too')}</label>
    <p className="bridge-small">{chunks.filter(chunk => !chunk.reviewed).length} {text('段待审核', 'chunks awaiting review')} · {chunks.length} {text('段总计', 'total chunks')}</p>
    {visible.map(chunk => <details className="bridge-edit-row" key={chunk.id}>
      <summary>{chunk.filename} · {chunk.page_number != null ? `${text('第', 'p. ')}${chunk.page_number}${text('页', '')}` : text('页码未知', 'page unknown')} · #{chunk.chunk_index + 1} · {chunk.chunk_type} · {chunk.reviewed ? text('已审核', 'reviewed') : text('待审核', 'unreviewed')}</summary>
      <p className="bridge-chunk-text">{chunk.text}</p>
      <form className="bridge-form" onSubmit={event => save(event, chunk)}>
        <label>{text('内容分类', 'Chunk type')}<select name="chunk_type" defaultValue={chunk.chunk_type}>{types.map(type => <option value={type} key={type}>{type}</option>)}</select></label>
        <label className="bridge-check"><input type="checkbox" name="reviewed" defaultChecked={chunk.reviewed} />{text('允许安全段用于学生检索', 'Approve safe chunk for student retrieval')}</label>
        <button className="bridge-primary" disabled={busy}>{text('保存分类', 'Save classification')}</button>
      </form>
    </details>)}
    {visible.length === 0 && <p>{text('所有资料段均已审核。', 'No chunks awaiting review.')}</p>}
  </div>;
}

import type { BridgeLanguage, BridgeSource, GroundingStatus } from '../../services/bridgeApi';

export default function BridgeEvidence({ status, sources, language }: {
  status: GroundingStatus;
  sources: BridgeSource[];
  language: BridgeLanguage;
}) {
  const grounded = status === 'GROUNDED';
  return <div className="bridge-evidence" aria-label={language === 'zh' ? '资料依据' : 'Evidence from module materials'}>
    <strong className={`bridge-status ${grounded ? 'bridge-status--grounded' : 'bridge-status--insufficient'}`}>
      {grounded ? 'GROUNDED' : 'INSUFFICIENT EVIDENCE'}
    </strong>
    {sources.length > 0 ? <><span className="bridge-sources-heading">{language === 'zh' ? '资料来源：' : 'Sources:'}</span><ul className="bridge-sources">
      {sources.map((source, index) => <li key={`${source.source_id || source.chunk_id || source.document || 'source'}-${index}`}>
        {source.document || source.reference || source.source_id || source.chunk_id || (language === 'zh' ? '课程资料' : 'Module material')}
        {source.page != null ? ` (${language === 'zh' ? '第' : 'p. '}${source.page}${language === 'zh' ? '页' : ''})` : ''}
        {source.chunk_id && source.document ? ` · ${source.chunk_id}` : ''}
      </li>)}
    </ul></> : <span className="bridge-no-sources">{language === 'zh' ? '未找到可核实的课程资料。' : 'No verifiable module source found.'}</span>}
  </div>;
}

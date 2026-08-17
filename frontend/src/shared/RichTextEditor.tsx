import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Underline from '@tiptap/extension-underline';
import { Bold, Italic, List, ListOrdered, Quote, Redo2, RemoveFormatting, Underline as UnderlineIcon, Undo2 } from 'lucide-react';
import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { cn } from './utils';

type Props = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  minHeight?: string;
  disabled?: boolean;
};

function ToolButton({active,disabled,label,onClick,children}:{active?:boolean;disabled?:boolean;label:string;onClick:()=>void;children:ReactNode}) {
  return <button type="button" title={label} aria-label={label} disabled={disabled} onMouseDown={event=>event.preventDefault()} onClick={onClick} className={cn('grid h-8 w-8 place-items-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-40',active&&'bg-blue-100 text-blue-700 hover:bg-blue-100 hover:text-blue-700')}>{children}</button>;
}

export function RichTextEditor({value,onChange,placeholder='Nhập nội dung...',className,minHeight='min-h-28',disabled=false}:Props) {
  const editor = useEditor({
    extensions: [StarterKit.configure({heading:false}), Underline, Placeholder.configure({placeholder})],
    content: value,
    editable: !disabled,
    editorProps: { attributes: { class: cn('rich-text-content px-4 py-3 text-sm leading-6 text-slate-800 outline-none', minHeight) } },
    onUpdate: ({ editor: instance }) => onChange(instance.getText({ blockSeparator: '\n' })),
  });

  useEffect(()=>{if(editor&&editor.getText({blockSeparator:'\n'})!==value)editor.commands.setContent(value,{emitUpdate:false})},[editor,value]);
  useEffect(()=>{editor?.setEditable(!disabled)},[editor,disabled]);
  if(!editor)return <div className={cn('field animate-pulse bg-slate-100',minHeight,className)}/>;
  const run=(command:()=>boolean)=>()=>command();
  return <div className={cn('overflow-hidden rounded-xl border border-slate-200 bg-white transition focus-within:border-blue-500 focus-within:ring-4 focus-within:ring-blue-100/80',disabled&&'bg-slate-50',className)}>
    {!disabled&&<div className="flex flex-wrap items-center gap-1 border-b border-slate-100 bg-slate-50 px-2 py-1.5">
      <ToolButton label="Hoàn tác" disabled={!editor.can().undo()} onClick={run(()=>editor.chain().focus().undo().run())}><Undo2 className="h-4 w-4"/></ToolButton>
      <ToolButton label="Làm lại" disabled={!editor.can().redo()} onClick={run(()=>editor.chain().focus().redo().run())}><Redo2 className="h-4 w-4"/></ToolButton>
      <span className="mx-1 h-5 w-px bg-slate-200"/>
      <ToolButton label="In đậm" active={editor.isActive('bold')} onClick={run(()=>editor.chain().focus().toggleBold().run())}><Bold className="h-4 w-4"/></ToolButton>
      <ToolButton label="In nghiêng" active={editor.isActive('italic')} onClick={run(()=>editor.chain().focus().toggleItalic().run())}><Italic className="h-4 w-4"/></ToolButton>
      <ToolButton label="Gạch chân" active={editor.isActive('underline')} onClick={run(()=>editor.chain().focus().toggleUnderline().run())}><UnderlineIcon className="h-4 w-4"/></ToolButton>
      <ToolButton label="Danh sách dấu đầu dòng" active={editor.isActive('bulletList')} onClick={run(()=>editor.chain().focus().toggleBulletList().run())}><List className="h-4 w-4"/></ToolButton>
      <ToolButton label="Danh sách đánh số" active={editor.isActive('orderedList')} onClick={run(()=>editor.chain().focus().toggleOrderedList().run())}><ListOrdered className="h-4 w-4"/></ToolButton>
      <ToolButton label="Trích dẫn" active={editor.isActive('blockquote')} onClick={run(()=>editor.chain().focus().toggleBlockquote().run())}><Quote className="h-4 w-4"/></ToolButton>
      <ToolButton label="Xóa định dạng" onClick={run(()=>editor.chain().focus().clearNodes().unsetAllMarks().run())}><RemoveFormatting className="h-4 w-4"/></ToolButton>
    </div>}
    <EditorContent editor={editor}/>
  </div>;
}

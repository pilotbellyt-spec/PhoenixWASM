use phoenix_ui_mobile::{self as ui, Node, Op};
use std::cell::RefCell;

thread_local! {
    static BUFFER: RefCell<Vec<u8>> = const { RefCell::new(Vec::new()) };
}

// JS copies the result before calling another export that can replace the buffer.
#[unsafe(no_mangle)]
pub extern "C" fn buffer_ptr() -> *const u8 {
    BUFFER.with_borrow(|bytes| bytes.as_ptr())
}

#[unsafe(no_mangle)]
pub extern "C" fn reserve_input(size: usize) -> *mut u8 {
    BUFFER.with_borrow_mut(|bytes| {
        bytes.resize(size, 0);
        bytes.as_mut_ptr()
    })
}

fn output(data: Vec<u8>) -> usize {
    let len = data.len();
    BUFFER.set(data);
    len
}

// A negative length identifies a UTF-8 error message in the same buffer.
#[unsafe(no_mangle)]
pub extern "C" fn describe_batch() -> isize {
    let result = BUFFER.with_borrow(|bytes| {
        let ops = ui::decode(bytes).map_err(|e| e.to_string())?;
        serde_json::to_vec(&ops).map_err(|e| e.to_string())
    });
    match result {
        Ok(json) => output(json) as isize,
        Err(error) => -(output(error.into_bytes()) as isize),
    }
}

fn create_node(node: &Node, ops: &mut Vec<Op>, next_id: &mut i32) -> i32 {
    let id = *next_id;
    *next_id += 1;
    ops.push(Op::Create {
        id,
        kind: node.kind.clone(),
        props: node.props.clone(),
    });
    if !node.kids.is_empty() {
        let ids = node
            .kids
            .iter()
            .map(|child| create_node(child, ops, next_id))
            .collect();
        ops.push(Op::Children { id, ids });
    }
    id
}

#[unsafe(no_mangle)]
pub extern "C" fn encode_template(index: u32) -> usize {
    let t = ui::templates();
    let templates = [
        &t.section,
        &t.header,
        &t.group,
        &t.switch_row,
        &t.divider,
        &t.button_row,
        &t.value_row,
        &t.input,
        &t.page,
        &t.sheet,
    ];
    let Some(node) = templates.get(index as usize) else {
        return 0;
    };
    let mut ops = Vec::new();
    let root = create_node(node, &mut ops, &mut 1);
    ops.push(Op::Root { id: root });
    output(ui::encode(&ops))
}

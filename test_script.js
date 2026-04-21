const jsdom = require('jsdom');
const { JSDOM } = jsdom;
const dom = new JSDOM('<!DOCTYPE html><p>Hello world</p>');
global.window = dom.window;
global.document = dom.window.document;
global.Node = dom.window.Node;

function typeWriterHTML(element, html, speed = 15) {
    element.innerHTML = '';
    let tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    
    function typeNode(node, targetEl, cb) {
        if (node.nodeType === Node.TEXT_NODE) {
            let text = node.textContent;
            let i = 0;
            let textNode = document.createTextNode('');
            targetEl.appendChild(textNode);
            function typeChar() {
                if (i < text.length) {
                    textNode.textContent += text.charAt(i);
                    i++;
                    typeChar();
                } else {
                    cb();
                }
            }
            typeChar();
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            let newEl = document.createElement(node.tagName);
            Array.from(node.attributes).forEach(attr => newEl.setAttribute(attr.name, attr.value));
            targetEl.appendChild(newEl);
            if (node.childNodes.length > 0) {
                typeNodes(Array.from(node.childNodes), newEl, cb);
            } else {
                cb();
            }
        } else {
            cb();
        }
    }

    function typeNodes(nodes, targetEl, cb) {
        let index = 0;
        function next() {
            if (index < nodes.length) {
                typeNode(nodes[index++], targetEl, next);
            } else if (cb) {
                cb();
            }
        }
        next();
    }

    typeNodes(Array.from(tempDiv.childNodes), element, () => {
        console.log('Finished typing');
        console.log(element.innerHTML);
    });
}

let div = document.createElement('div');
typeWriterHTML(div, '<b>Hello</b> <i>World</i>', 0);

import zmq
import sys
import time
import json
import random
import threading
import select
import os
import urllib
import re

class Client:
    next_req_id = 1
    LOC = 'locate'
    GET = 'get' 
    def __init__(self, client_ip):
        self.ip = client_ip
        self.context = zmq.Context()
        ip,port = (client_ip).split(':')
        self.s_rep = self.context.socket(zmq.REP)
        self.s_rep.bind("tcp://%s:%s" %(ip,port))
        
    
    def get_html_of(self, urls, ip):
        for url in urls:
            threading.Thread(target=self.request_html, args=(url,ip)).start()
            

    def request_html(self, url, ip):
        get_ip = self.send_request(ip, Client.LOC,url)
        print(get_ip)
        if get_ip:
            html = self.send_request(get_ip, Client.GET, url)
            return html
        return None
    
    def send_request(self, ip_port, head,body):
        s_req = self.make_req_socket(ip_port)
        # s_req.setsockopt( zmq.RCVTIMEO, 3000 ) # milliseconds
        s_req.send_string(head + " " + body)
        try:
            return s_req.recv_string() # response
        except:
            return None # timeout
  
    def make_req_socket(self, ip_port):
        s_req = self.context.socket(zmq.REQ)
        ip,port = (ip_port).split(':')
        s_req.connect("tcp://%s:%s" %(ip,port))
        return s_req

    def base_scrap(self,req_addr,url,depth):
        
        folder = self.get_folder_name(url)
        folder = 'Pedidos/'+folder
        os.makedirs(folder)

        html = self.request_html(url,req_addr)
        
        links = self.get_hrefs(html)
        for key in links:
            if links[key].find('http') == 0:
                self.scrap(req_addr,links[key],depth-1,folder,key)

        html = self.update_html(links,html)
        
        file = open(f'./{folder}/base.html', 'x',encoding='utf8')
        file.write(html)
        file.close()

    def scrap(self,req_addr,url,depth, base_path='',folder_name=0):
        if depth<0:
            return
        
        folder =f'{base_path}/{folder_name}'
        os.makedirs(folder)
        
        html = self.request_html(url,req_addr)
        links = self.get_hrefs(html)
        for key in links:
            if links[key].find('http') == 0:
                self.scrap(req_addr,links[key],depth-1,folder,key)

        html = self.update_html(links,html)
        
        file = open(f'./{folder}/{folder_name}.html', 'x', encoding='utf8')
        file.write(html)
        file.close()

    def update_html(self,links,html):
        
        keys= list(links.keys())
        keys.sort()
        if not keys:
            return html
        index = keys[0]+len(links[keys[0]])
        
        aux=html[:keys[0]]

        for i in range(len(keys)):
            index = keys[i]+len(links[keys[i]])
            if i+1 < len(keys):
                aux+=str(keys[i])+'/'+str(keys[i])+'.html'+html[index:keys[i+1]]
            else:
                aux+=html[:keys[i]]+str(keys[i])+'/'+str(keys[i])+'.html'+html[index:]
        return aux

    def get_hrefs(self,html):       
        indexes =[m.start() for m in re.finditer(' href=', html)]        
        links= {}
        
        for i in indexes:
            index =html.find('"',i+7)
            links[i+7] = html[i+7:index]
        return links

    def get_folder_name(self,url):
        self.update_id()
        id = self.next_req_id
        self.next_req_id+=1
        
        url = url.split('//',1)
        try:
            url = url[1].split('/',1)
        except IndexError:
            pass
        return f'{id}- {url[0]}'
    
    def update_id(self):
        folders_in_pedidos = next(os.walk('./Pedidos'))[1]
        if folders_in_pedidos:
            for i in range(len(folders_in_pedidos)-1,-1,-1):
                try:
                    self.next_req_id = int(folders_in_pedidos[i].split('-',1)[0]) + 1
                    break
                except ValueError:
                    pass


def main():
    # client_ip = sys.argv[1]
    client_ip = '127.0.0.1:5000'

    c = Client(client_ip)
    c.base_scrap('127.0.0.1:5003','https://evea.uh.cu', 1 )
    # h = c.request_html('url', '127.0.0.1:5001')
    # print(h)
    # os.makedirs('Pedidos/1- www.google.com.cu')

    # cli = Client('127.0.0.1:5000')
    # print(cli.get_folder_name('www.google.com.cu'))
    # print(next(os.walk('./Pedidos'))[1])
    # str = 'hai'
    # print(str[0])
    # links = {28 : 'WHatdashkd' , 27: 'dahsd'}
    # hai= links.keys
    # hai = list(hai())
    # print(hai)
    # for i in range(len(hai)):
    #     print(hai[i])

    # file = open('./Pedidos/hello.txt', 'x')
    # file.write("Hello World!")
    # file.close()


if __name__ == "__main__":
    main()
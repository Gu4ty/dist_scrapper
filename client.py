from typing import Collection
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
import shutil
import argparse
import collections
from zmq.sugar.frame import Message

class Client:
    next_req_id = 1
    LOC = 'locate'
    GET = 'get' 
    BR = 'bad request'
    BR_TEXT = 'Scrap could not be performed, url did not retrieve information. (Url might not be correct.)'
    TO_TEXT = 'Connection timed out.'

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
        if get_ip:
            html = self.send_request(get_ip, Client.GET, url)
            return html
        return None
    
    def send_request(self, ip_port, head,body):
        s_req = self.make_req_socket(ip_port)
        s_req.setsockopt( zmq.RCVTIMEO, 45000 ) # milliseconds
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
        folder = 'Requests/'+folder
        os.makedirs(folder)

        html = self.request_html(url,req_addr)
        if html == self.BR:
            return self.BR_TEXT
        if html is None:
            shutil.rmtree(folder)
            return self.TO_TEXT

        links = self.get_hrefs(html)
        for key in links:
            if links[key].find('http') == 0:
                broken_request = self.scrap(req_addr,links[key],depth-1,folder,key)
                if broken_request:
                    shutil.rmtree(folder)
                    return self.TO_TEXT
        
        html = self.update_html(links,html)

        file = open(f'./{folder}/base.html', 'x',encoding='utf8')
        file.write(html)
        file.close()

        return f'Scrap saved to {os.getcwd()}/{folder}'

    def scrap(self,req_addr,url,depth, base_path='',folder_name=0):
        if depth<0:
            return
        
        folder =f'{base_path}/{folder_name}'
        os.makedirs(folder)
        
        html = self.request_html(url,req_addr)
        if html is None:
            return True

        links = self.get_hrefs(html)

        for key in links:
            if links[key].find('http') == 0:
                broken_request = self.scrap(req_addr,links[key],depth-1,folder,key)
                if broken_request:
                    return True

        html = self.update_html(links,html)
       
        extension = '.css' if url.endswith('.css') else '.html'
        file = open(f'./{folder}/{folder_name}{extension}', 'x', encoding='utf8')
        file.write(html)
        file.close()

        return False

    def update_html(self,links,html):
        
        keys= list(links.keys())
        keys.sort()
        if not keys:
            return html
        index = keys[0]+len(links[keys[0]])
        aux = collections.deque()
        aux.append(html[:keys[0]])

        for i in range(len(keys)):
            link = links[keys[i]]
            extension = '.css' if link.endswith('.css') else '.html'
            index = keys[i]+len(link)
            if i+1 < len(keys):
                aux.append(str(keys[i])+'/'+str(keys[i])+extension+html[index:keys[i+1]])
            else:
                aux.append(str(keys[i])+'/'+str(keys[i])+extension+html[index:])
        return ''.join(aux)

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
        folders_in_Requests = next(os.walk('./Requests'))[1]
        if folders_in_Requests:
            for i in range(len(folders_in_Requests)-1,-1,-1):
                try:
                    self.next_req_id = int(folders_in_Requests[i].split('-',1)[0]) + 1
                    break
                except ValueError:
                    pass
    
    def process_input(self):
        print("\033c")
        print("URL to scrap:")
        url = input()

        depth = None
        correct_depth = False
        while not correct_depth:
            print("Depth:")
            try:
                depth = int(input())
                correct_depth = True
            except ValueError:
                print('\n Depth must be integer.\n')
        return (url,depth)
    
    def run(self,req_addr):
        while True:
            url,depth = self.process_input()
            
            i=3
            while i:
                resp_message = self.base_scrap(req_addr,url, depth)
                
                print(f'\n{resp_message}')
                if resp_message == self.TO_TEXT:
                    i-=1
                else:
                    print('\n Press Enter to continue...')
                    input()
                    break

def main():

    params = sys.argv[1:]
    parser = argparse.ArgumentParser(prog='PROG')
    parser.add_argument('-my_addr', type=str) 
    parser.add_argument('-entry_addr',type=str)
    args =parser.parse_args(params)
    args = vars(args)
    try:
        os.makedirs('Requests')
    except FileExistsError:
        pass

    c = Client(args['my_addr'])
    c.run(args['entry_addr'])


if __name__ == "__main__":
    main()
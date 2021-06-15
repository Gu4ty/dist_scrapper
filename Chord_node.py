import zmq
import sys
import time
import json
import random
import threading
import select
import hashlib
import urllib.request
import re

def split_ip(ip):
    return ip.split(':')

class Chord_Node:
    #=====Requests strings=====
    CPF = 'closest_preceding_finger'
    FS = 'find_successor'
    UPDATE_PRED = 'update_predeccessor'
    UFT = 'update_finger_table'
    RFT = 'request_finger_table'
    RSL = 'request_succesor_list'
    NOTIFY = 'notify'
    ALIVE = 'alive'
    PRQ = 'pull_request'
    LC = 'locate'
    GET = 'get'
    #==========================
    
    def __init__(self, id, my_ip, m ,entry_point = None):
        
        self.context = zmq.Context()
        ip,port = split_ip(my_ip)
        self.s_rep = self.context.socket(zmq.REP)
        self.s_rep.bind("tcp://%s:%s" %(ip,port))

        self.id = id
        self.ip = my_ip
        self.m = m # number of bits
        self.r = m # number of succesors
        self.k = self.r//2 + 1 # number of nodes to replicate data
        self.k = 1
        #finger[i] = node with id >= id + 2^(i-1)
        self.finger = [(self.id,self.ip) for _ in range(m+1)] #finger[0] = Predecessor
        self.succesors = [(self.id,self.ip) for _ in range(m)]
        
        self.data = {}
        self.latest_data = [] 
        self.predecessors_data = {}
        
        self.lock_finger = threading.Lock()
        self.lock_succesors = threading.Lock()
        self.lock_predecessors_data = threading.Lock()
        self.lock_data = threading.Lock()

        if entry_point:
            self.join(entry_point)
        
        
        

        #-----------handlers-----------
        self.handlers = {}
        self.handlers[Chord_Node.CPF] = self.request_closest_preceding_finger_handler
        self.handlers[Chord_Node.FS] =  self.request_successor_handler
        self.handlers[Chord_Node.UPDATE_PRED] = self.request_update_predeccessor_handler
        self.handlers[Chord_Node.UFT] = self.request_update_finger_handler
        self.handlers[Chord_Node.RFT] = self.request_finger_table_handler
        self.handlers[Chord_Node.NOTIFY] = self.request_notify_handler
        self.handlers[Chord_Node.ALIVE] = self.request_is_alive_handler
        self.handlers[Chord_Node.RSL] = self.request_succesor_list_handler
        self.handlers[Chord_Node.PRQ] = self.request_pull_handler
        self.handlers[Chord_Node.LC] = self.request_locate
        self.handlers[Chord_Node.GET] = self.request_get
        #------------------------------

        
        threading.Thread(target=self.infinit_fix_fingers, args=()).start()
        threading.Thread(target=self.infinit_stabilize, args=()).start()
        threading.Thread(target=self.infinit_fix_succesors, args=()).start()
        threading.Thread(target=self.infinit_replicate, args=()).start()
        
        self.insert_data((self.id, 'google ' + str(self.id)) , str(self.id) * 5)

        self.run()


    #============Join node============
    def join(self,entry_point):
        self.init_finger_table(entry_point)
        self.succesors = [self.finger[1] for _ in range(self.r)]
        self.update_others()
             

    def init_finger_table(self, ip):
        
        node_succ = self.request_successor(ip, self.start_idx(1))
        if not node_succ:
            print('Unstable network, try again later')
            exit()
        self.finger[1] =  (node_succ['id'], node_succ['ip'])
        self.finger[0] = node_succ['fg'][0] 
        
        self.request_update_predeccessor(node_succ['ip'])
        for i in range(1,self.m):
            node =  self.finger[i] #id,ip
            start = self.start_idx(i+1)
            if self.inbetween(start,self.id,True , node[0], False ):
                self.finger[i+1] = self.finger[i]
            else:
                succ_node = self.request_successor(ip,start)
                if not succ_node:
                    print('Unstable network, try again later')
                    exit()
                self.finger[i+1] = (succ_node['id'], succ_node['ip'])

    def update_others(self):
        for i in range(1,self.m+1):
           
            node = self.find_predecessor( (self.id - (2**(i-1))   + 2**self.m ) % 2**self.m   )
            if node['id'] != self.id:
                self.request_update_finger((self.id,self.ip),node['ip'], i)
                
        
                
    def update_finger_table(self,n,i):
        node =  self.finger[i]
        if self.inbetween(n[0], self.id,True , node[0],False ):
            self.finger[i] = n
            pred_node = self.finger[0]
            if pred_node[0] != n[0]:
                self.request_update_finger(n,pred_node[1], i)
               
   
    #============End Join node============

    #============Stabilization============
    def stabilize(self):
        self.lock_finger.acquire()
        successor_finger_table = self.request_finger_table(self.finger[1][1])
        take_care_of = []
        if successor_finger_table:
            
            predeccessor = successor_finger_table[0]
            if self.inbetween(predeccessor[0], self.id,False , self.finger[1][0],False):
                self.finger[1] = predeccessor
                self.succesors[0]= predeccessor
           
        else:
            take_care_of.append(self.finger[1][0])
            for i in range(1, len(self.succesors)):
                n = self.succesors[i]
                if self.is_alive(n[1]):
                    self.finger[1]= n
                    break
                else:
                    take_care_of.append(n[0])
        
        self.request_notify(self.finger[1][1], take_care_of)
        
        self.lock_finger.release()
        
    
    def fix_fingers(self):
       
        self.lock_finger.acquire()
        i = random.randint(1,self.m)
        node = self.find_succesor(self.start_idx(i))
        if node:
            self.finger[i] = (node['id'], node['ip'])
        self.lock_finger.release()
    
    def fix_succesors(self):
        self.lock_succesors.acquire()
        self.succesors[0]= self.finger[1]
        i = random.randint(1,self.r-1)
        succesor_node = self.succesors[i-1]
        node = self.find_succesor( (succesor_node[0] + 1) % (2**self.m) )
        if  node:
            self.succesors[i] = ( node['id'], node['ip'] )
        self.lock_succesors.release()

    def infinit_stabilize(self):
        while True:
            print("\033c")
            self.print_me()   
            self.stabilize()
            time.sleep(1)

    def infinit_fix_fingers(self):
        while True:
            self.fix_fingers()
            time.sleep(1)
    
    def infinit_fix_succesors(self):
        while True:
            self.fix_succesors()
            time.sleep(1)
            
    #============End Stabilization============

    def find_succesor(self, idx):
        
        node = self.find_predecessor(idx)
        if not node:
            return None
        succesors = self.succesors
        if node['id'] != self.id:
            succesors = self.request_succesor_list(node['ip'])
            if not succesors:
                return None
        next_node = next( (n for n in succesors  if self.is_alive(n[1]) ) , None)
        if not next_node:
            return None
        if next_node[0] == self.id:
            return self.to_dicctionary()
        
        node_succ_finger = self.request_finger_table(next_node[1])
        if node_succ_finger:
            return {'id': next_node[0], 'ip': next_node[1], 'fg': node_succ_finger}

        return None

    def find_predecessor(self, idx):
        node = (self.id, self.ip)
        omit = []
        while(True):
            id = node[0]
            ip = node[1]
            ft = self.request_finger_table(node[1])
            if not ft:
                return None
            node_succ_id, node_succ_ip = ft[1]
            if self.inbetween(idx, id,False, node_succ_id,True ):
                return {'id': node[0], 'ip': node[1], 'fg': ft}
            if id == self.id :
                node = self.closest_preceding_finger(idx, omit)
            else:
                node = self.request_closest_preceding_finger(node[1],idx,omit)
                if not node:
                    return None

            alive = self.is_alive(node[1])
            while(not alive):
                omit.append(node[0])
                if id == self.id :
                    node = self.closest_preceding_finger(idx, omit)
                else:
                    node = self.request_closest_preceding_finger(ip,idx,omit)
                    if not node:
                        return None
                alive = self.is_alive(node[1])

            if node[0] == id:
                return {'id': node[0], 'ip': node[1], 'fg': ft}

    def closest_preceding_finger(self,idx , omit):
        for i in reversed(range(1,self.m+1)):
            node_id,node_ip = self.finger[i]
            if self.inbetween(node_id, self.id,False, idx,False ):
                if node_id not in omit:
                    return (node_id, node_ip)
        
        closest = next( (n for n in reversed(self.succesors)  if n[0] not in omit and self.inbetween(n[0], self.id,False, idx, False) ) , None)
        if closest:
            return closest
        return (self.id,self.ip)

    #============Send Requests============
    
    def request_successor(self, ip_port, idx):
        response = self.send_request(ip_port, Chord_Node.FS, str(idx))
        if response:
            return json.loads(response)
        return None
    
    def request_closest_preceding_finger(self, ip_port,idx, omit):
        response = self.send_request(ip_port, Chord_Node.CPF, str(idx) + " " + json.dumps(omit))
        if response:
            node = json.loads(response)
            return node
        return None

    def request_update_predeccessor(self, ip_port):
        response = self.send_request(ip_port,Chord_Node.UPDATE_PRED, json.dumps((self.id,self.ip)) )
        if response:
            response = json.loads(response)
            if response:
                for d in response:
                    self.insert_data(tuple(d['k']), d['v'] )
                #dic = { tuple(d['k']): d['v']  for d in response}
            return "OK"
        return None

    def request_update_finger(self,node,ip_port,i):
        response = self.send_request(ip_port,Chord_Node.UFT, json.dumps([node,i] ) )
        if response:
            return "OK"
        return None
    
    def request_finger_table(self, ip_port):
        if self.ip == ip_port:
            return self.finger
        response = self.send_request(ip_port,Chord_Node.RFT, " " )
        if response:
            return json.loads(response)
        return None

    def request_succesor_list(self,ip_port):
        response = self.send_request(ip_port, Chord_Node.RSL, " ")
        if response:
            return json.loads(response)
        return None
    
    def request_notify(self,ip_port, take_care_of):
        response = self.send_request(ip_port,Chord_Node.NOTIFY,json.dumps((self.id,self.ip)) + "&" + json.dumps(take_care_of) )
        if response:
            return "OK"
        return None
    
    def request_pull(self, ip_port):
        response = self.send_request(ip_port,Chord_Node.PRQ, str(self.id) + " " + json.dumps(self.latest_data) )
        return response

    #============End Send Requests============

    #============Handling Requests============
    def request_successor_handler(self, body):
        idx = int(body)
        node = self.find_succesor(idx)
        self.s_rep.send_string(json.dumps(node) )
    
    def request_closest_preceding_finger_handler(self, body):
        idx, omit = body.split(" ",1)
        idx = int(idx)
        omit = json.loads(omit)
        node = self.closest_preceding_finger(idx,omit)
        self.s_rep.send_string(json.dumps(node))

    def request_update_predeccessor_handler(self, body):
        self.erase_last_predecessor_data()
        prev_pred = self.finger[0][0]
        self.finger[0] = json.loads(body)
        send_data = {}
        keys_to_erase = []
        self.lock_data.acquire()
        for k,v in self.data.items():
            if self.inbetween(k[0], prev_pred, False, self.finger[0][0], True):
                send_data[k] = v
                keys_to_erase.append(k)
        for k in keys_to_erase:
            self.erase_data(k)

        
        to_list = [{'k':k, 'v': v} for k,v in send_data.items()]
        self.lock_data.release()
        self.s_rep.send_string(json.dumps(to_list))

    def request_update_finger_handler(self, body):
        node, i = json.loads(body)
        self.update_finger_table(node,i)
        self.s_rep.send_string('OK')
       

    def request_finger_table_handler(self, body = None):
        self.s_rep.send_string(json.dumps(self.finger))
    
    def request_succesor_list_handler(self, body):
        self.s_rep.send_string(json.dumps(self.succesors))
    
    def request_notify_handler(self, body):
        p, take_care = body.split("&", 1)
        p = json.loads(p)
        take_care = json.loads(take_care)
        if self.is_alive(self.finger[0][1]):
            if(self.inbetween(p[0], self.finger[0][0],False, self.id,False  )):
                self.erase_last_predecessor_data()
                self.finger[0] = p
        else:
            self.finger[0] = p
            self.take_care_of(take_care)

        self.s_rep.send_string('OK')
    def request_is_alive_handler(self, body):
        self.s_rep.send_string("OK")
    
    def request_pull_handler(self, body):
        id, data = body.split(" ", 1)
        id = int(id)
        data = json.loads(data)
        self.lock_predecessors_data.acquire()
        try:
            self.predecessors_data[id]
        except KeyError:
            self.predecessors_data[id] = {}
        
        predecessor_data = self.predecessors_data[id]
        for d in data:
            predecessor_data[tuple(d[0]) ] = d[1]

        self.lock_predecessors_data.release()
        self.s_rep.send_string('OK')
    #============End Handling Requests============
    
    #============Data============
    
    def insert_data(self,key,value):
        self.lock_data.acquire()
        try:
            self.data[key]
        except KeyError:
            self.data[key] = value
            if len(self.latest_data) == 100:
                self.latest_data.pop(0)
            self.latest_data.append((key,value))
        self.lock_data.release()

    def erase_data(self , key):
        del self.data[key]
        for i in range(len(self.latest_data)):
            if self.latest_data[i][0] == key:
                del self.latest_data[i]
                break
        

    def erase_last_predecessor_data(self):
        self.lock_predecessors_data.acquire()
        p = [id for id in self.predecessors_data]
        if not p:
            self.lock_predecessors_data.release()
            return
        p.sort()
        to_erase = 0
        if p[-1] > self.id:
            to_erase = p[-1]
        else:
            to_erase = p[0]
        del self.predecessors_data[to_erase]
        
        self.lock_predecessors_data.release()
       
        
    def replicate(self):
        i = random.randint(0, self.k-1)
        node = self.succesors[i]
        if node[0] != self.id and self.data:
            self.request_pull(node[1]) 
    
    def infinit_replicate(self):
        while True:
            self.replicate()
            time.sleep(1)

    #============End Data============


    #============Hash================

    def int_hash(self,str):
        bytes_rep = hashlib.sha256(bytes(str, 'utf-8')).digest()        
        return int.from_bytes(bytes_rep,"big") % (2**self.m)
        

    #============End Hash============
    #============Scraper=============

    def request_locate(self, body):
        node = self.find_predecessor(self.int_hash(body))
        self.s_rep.send_string(node['ip'])

    def request_get(self,url):
        hash = self.int_hash(url)
        html = None
        try:
            html = self.data[(hash,url)]
        except KeyError:
            webUrl  = urllib.request.urlopen(url)
            html = str(webUrl.read())[2:-1]
            self.insert_data((hash,url), html)
        
        self.s_rep(html)

        # url, depth = body.split(" ",1)
        # depth = int(depth)
        # webUrl  = urllib.request.urlopen(url)

        # data = str(webUrl.read())[2:]
       
        # indexes =[m.start() for m in re.finditer(' href=', data)]
        
        # links= {}
        
        # for i in indexes:
        #     index =data.find('"',i+7)
        #     links[i] = data[i+7:index]

        # return None
            


    #============End Scraper=========

    #============Utils============
    
    def take_care_of(self, take_care):
        self.lock_predecessors_data.acquire()
        for id in take_care:
            for k,v in self.predecessors_data[id].items():
                
                self.insert_data(k,v)
            del self.predecessors_data[id]
        self.lock_predecessors_data.release()

    def is_alive(self,ip_port):
        if ip_port == self.ip:
            return "OK"
        return self.send_request(ip_port,Chord_Node.ALIVE, ' ')

    def send_request(self, ip_port, head,body):
        s_req = self.make_req_socket(ip_port)
        s_req.setsockopt( zmq.RCVTIMEO, 1000 ) # milliseconds
        s_req.send_string(head + " " + body)
        try:
            return s_req.recv_string() # response
        except:
            return None # timeout

    def print_me(self):
        self.lock_data.acquire()
        self.lock_predecessors_data.acquire()
        print("Node id: ", self.id)
        print("Node ip: ", self.ip)
        print("Predecessor: ", self.finger[0])
        for i in range(1, self.m + 1):
            print(f'Finger[{i}]= (node id: {self.finger[i][0]} , node ip: {self.finger[i][1]} )')
        print("Successors list: ", self.succesors)
        print("Data:")
        print(self.data)
        print("Replicated data:")
        print(self.predecessors_data)
        self.lock_data.release()
        self.lock_predecessors_data.release()

    def inbetween(self,key, lwb, lequal, upb, requal):
        
        if key== upb or key == lwb:
                if key == upb:
                    return requal
                if key == lwb:
                    return lequal

        if lwb == upb:
            return True


        if lwb <= upb:
            return key >= lwb and key <= upb
        else:
            return not (key <= lwb and key >= upb  )



    def start_idx(self,k):
        return (self.id + 2**(k-1)) % (2**self.m)

    def to_json(self):
        return json.dumps(self.to_dicctionary())

    def to_dicctionary(self):
        node = {}
        node['id'] = self.id
        node['ip'] = self.ip
        node['fg'] = self.finger
        return node
    
    def make_req_socket(self, ip_port):
        s_req = self.context.socket(zmq.REQ)
        ip, port = split_ip(ip_port)
        s_req.connect("tcp://%s:%s" %(ip,port))
        return s_req
    
    #============end Utils============


    def run(self):
        while(True): 
            
            try:
                req = self.s_rep.recv_string()
                header,body = req.split(" ",1)
                self.handlers[header](body)
            except KeyboardInterrupt:
                break    

def main():
    id = int(sys.argv[1])
    ip = sys.argv[2]
    m = int(sys.argv[3])
    entry = None
    if len(sys.argv) ==5:
        entry = sys.argv[4]
    
    n = Chord_Node(id,ip,m,entry)

if __name__ == "__main__":
    main()